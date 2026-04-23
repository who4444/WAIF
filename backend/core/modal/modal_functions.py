import os
import io
import modal
import torch
import numpy as np
from typing import Optional

# ─── Config ───────────────────────────────────────────────────────────────────

app = modal.App("waif-gpu-service")

# Storage for ~20GB of model weights
weights_volume = modal.Volume.from_name("waif-weights", create_if_missing=True)

gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "git", "libsndfile1", "portaudio19-dev", "build-essential")
    .pip_install(
        "faster-whisper",
        "fish-speech",
        "torch",
        "torchaudio",
        "numpy",
        "huggingface_hub",
        "sentence-transformers",
        "librosa",
        "scipy",
        "pyaudio",
    )
    .env({"PYTHONPATH": "/root/fish-speech", "COMPILE": "1"})
)

# ─── 1. Transcription (STT) ───────────────────────────────────────────────────

@app.cls(
    image=gpu_image,
    gpu="T4",
    volumes={"/weights": weights_volume},
    scaledown_window=300
)
class WhisperSTT:
    @modal.enter()
    def load_model(self):
        from faster_whisper import WhisperModel
        # Medium is the sweet spot for speed/accuracy
        self.model = WhisperModel(
            "medium.en", 
            device="cuda", 
            compute_type="float16",
            download_root="/weights/whisper"
        )

    @modal.method()
    def transcribe(self, audio_bytes: bytes):
        segments, _ = self.model.transcribe(io.BytesIO(audio_bytes), beam_size=5)
        return " ".join([s.text for s in segments]).strip()

# ─── 2. Speech Synthesis (TTS) ────────────────────────────────────────────────

@app.cls(
    image=gpu_image,
    gpu="A10G", # S2-Pro needs 24GB VRAM and fast cores
    volumes={"/weights": weights_volume},
    scaledown_window=600
)
class FishSpeechTTS:
    @modal.enter()
    def load_model(self):
        import librosa

        from fish_speech.models.text2semantic.inference import load_model as load_llama
        from fish_speech.models.dac.inference import load_model as load_codec
        
        path = "/weights/fish-speech-1.5"
        print("💽 Loading FishSpeech S2-Pro...")
        self.llama = load_llama(path, device="cuda")
        self.codec = load_codec(f"{path}/firefly-gan-vq-fsq-8x1024-21hz-generator.pth", device="cuda")

        voice_wav_path = "/weights/voices/main_voice.wav"
        voice_text_path = "/weights/voices/main_voice.txt"

        print(f"🎙️ Pre-encoding main voice: {voice_wav_path}")
        audio, _ = librosa.load(voice_wav_path, sr=self.codec.sampling_rate)
        audio_tensor = torch.from_numpy(audio).to("cuda").unsqueeze(0).unsqueeze(0)
        
        with torch.no_grad():
            # Pre-calculate the VQ prompt tokens once
            vqs = self.codec.encode(audio_tensor)
            self.main_voice_tokens = vqs[0] # Shape: [num_codebooks, seq_len]
        
        # Load the reference text (crucial for prosody alignment)
        with open(voice_text_path, "r") as f:
            self.main_voice_text = f.read().strip()
    
    @modal.method()
    def generate(
        self, 
        text: str, 
        voice_ref_id: Optional[str] = None,
        ref_audio_bytes: Optional[bytes] = None, 
        ref_text: str = "",
        params: dict = None
    ) -> bytes:
        from fish_speech.models.text2semantic.inference import generate_tokens
        from fish_speech.models.dac.inference import decode_audio
        import librosa
        import torch
        import io
        import numpy as np
        import scipy.io.wavfile as wavfile
        import os
        
        if voice_ref_id:
            audio_path = f"/weights/voices/{voice_ref_id}.wav"
            text_path = f"/weights/voices/{voice_ref_id}.txt"
            
            if os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    ref_audio_bytes = f.read()
                if os.path.exists(text_path):
                    with open(text_path, "r") as f:
                        ref_text = f.read().strip()
            else:
                print(f"[tts] Warning: Voice {voice_ref_id} not found at {audio_path}")
        # Default generation parameters
        gen_kwargs = {
            "top_p": 0.7,
            "repetition_penalty": 1.2,
            "temperature": 0.7,
            "max_new_tokens": 1024,
            "chunk_length": 200,
        }
        if params: gen_kwargs.update(params)

        prompt_tokens = None
        
        # ─── 1. Encode Reference Audio (Zero-Shot Logic) ──────────────────────
        if ref_audio_bytes:
            print(f"[tts] Encoding reference voice (ref_text: '{ref_text[:30]}...')")
            
            # Load bytes and resample to the Codec's native rate (usually 44.1kHz)
            # self.codec.sampling_rate is typically 44100
            audio, _ = librosa.load(
                io.BytesIO(ref_audio_bytes), 
                sr=self.codec.sampling_rate
            )
            
            # Convert to torch tensor [Batch, Channels, Time]
            audio_tensor = torch.from_numpy(audio).to("cuda").unsqueeze(0).unsqueeze(0)
            
            with torch.no_grad():
                # Extract VQ indices. Shape: [1, num_codebooks, seq_len]
                # In FishSpeech S2, the first codebook is the 'Semantic' one
                # but we pass the full tensor to condition the style.
                vqs = self.codec.encode(audio_tensor)
                
                # generate_tokens expects prompt_tokens to be [num_codebooks, seq_len]
                prompt_tokens = vqs[0] 

        # ─── 2. Text -> Semantic Tokens (Llama Inference) ─────────────────────
        with torch.no_grad():
            # generate_tokens handles the 'Slow AR' (Text -> Codebook 0)
            # and 'Fast AR' (Codebook 0 -> Codebooks 1-N) stages in S2.
            codes = generate_tokens(
                model=self.llama,
                text=text,
                prompt_text=ref_text,       # The transcription of the reference
                prompt_tokens=prompt_tokens, # The VQ tokens extracted above
                device="cuda",
                **gen_kwargs
            )
            
        # ─── 3. Semantic Tokens -> Waveform (DAC Decoding) ─────────────────────
        # codes shape is [num_codebooks, total_seq_len]
        audio_out = decode_audio(self.codec, codes)
        
        # Move to CPU and normalize to 16-bit PCM for WAV
        audio_np = audio_out.cpu().numpy()
        audio_int16 = (audio_np * 32767).astype(np.int16)
        
        buffer = io.BytesIO()
        wavfile.write(buffer, self.codec.sampling_rate, audio_int16)
        
        print(f"[tts] Successfully generated {len(audio_int16)/self.codec.sampling_rate:.2f}s of audio")
        return buffer.getvalue()
# ─── 3. Weight Downloader (Run Once) ──────────────────────────────────────────

@app.function(image=gpu_image, volumes={"/weights": weights_volume})
def setup():
    from huggingface_hub import snapshot_download
    print("Downloading weights...")
    snapshot_download(repo_id="systran/faster-whisper-medium.en", local_dir="/weights/whisper")
    snapshot_download(repo_id="fishaudio/fish-speech-1.5", local_dir="/weights/fish-speech-1.5")
    weights_volume.commit()
    print("✅ Setup complete.")