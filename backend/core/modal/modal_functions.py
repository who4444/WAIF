import os
import io
import subprocess
import modal
import torch
import numpy as np
from typing import Optional, List

# ─── Config ───────────────────────────────────────────────────────────────────

app = modal.App("waif-gpu-service")

# Storage for ~20GB of model weights
weights_volume = modal.Volume.from_name("waif-weights", create_if_missing=True)

base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg",
        "git",
        "libsndfile1",
        "portaudio19-dev",
        "build-essential",
        "curl",
    )
    .pip_install(
        "faster-whisper",
        "torch==2.8.0",          # pin — match fish-speech requirement
        "torchaudio==2.8.0",
        "numpy",
        "huggingface_hub",
        "scipy",
        "httpx",                  # used by the Modal TTS wrapper to call api_server
        "omegaconf",
        "hydra-core",
        "sentence-transformers",  # for Embeddings class
    )
    # Install fish-speech from source so tools/ directory is present
    .run_commands(
        "pip install git+https://github.com/fishaudio/fish-speech.git",
        # Verify that api_server.py was installed with the package
        "python -c \"import tools; import pathlib; "
        "p = pathlib.Path(str(tools.__path__[0])) / 'api_server.py'; "
        "print('api_server found:', p.exists())\"",
        # pyrootutils.setup_root() in api_server.py looks for .project-root indicator.
        # The file lives at the repo root but isn't shipped by the package. Create it
        # where pyrootutils expects it — one level above the tools/ package directory.
        "python -c \"import tools; import pathlib; "
        "p = pathlib.Path(str(tools.__path__[0])).parent / '.project-root'; "
        "p.write_text(''); print('.project-root created:', p)\"",
    )
)
 
 
# ─── 1. STT — Whisper (unchanged, was already correct) ───────────────────────
 
@app.cls(
    image=base_image,
    gpu="T4",
    volumes={"/weights": weights_volume},
    scaledown_window=300,
)
class WhisperSTT:
    @modal.enter()
    def load_model(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(
            "medium.en",
            device="cuda",
            compute_type="float16",
            download_root="/weights/whisper",
        )
 
    @modal.method()
    def transcribe(self, audio_bytes: bytes) -> str:
        segments, _ = self.model.transcribe(io.BytesIO(audio_bytes), beam_size=5)
        return " ".join(s.text for s in segments).strip()
 
 
# ─── 2. TTS — Fish Speech S2-Pro via official api_server.py ──────────────────
#
# We run `python tools/api_server.py` as a subprocess inside the container.
# Modal's @web_endpoint decorator exposes the server's HTTP interface directly.
# This is the *only* stable way to run S2-Pro: the upstream authors designed
# api_server.py as the inference entry-point; its internals change between
# releases and should not be imported directly.
#
# GPU choice:
#   A10G  (24 GB) — minimum viable, no --compile (OOM risk with CUDA graphs)
#   A100  (40 GB) — recommended; enables --compile for ~2x throughput
#   H100  (80 GB) — best; matches Fish Audio's published RTF of 0.195
 
FISH_SERVER_PORT = 8080
FISH_CHECKPOINT  = "/weights/s2-pro"
FISH_CODEC_PATH  = "/weights/s2-pro/codec.pth"
USE_COMPILE      = False   # Set True only on A100/H100 — OOMs on A10G
 
@app.cls(
    image=base_image,
    gpu="A10G",             # minimum for S2-Pro (24 GB VRAM)
    volumes={"/weights": weights_volume},
    scaledown_window=600)
class FishSpeechTTS:
    """
    Wraps the official fish-speech api_server.py.
 
    The server is started once per container in @modal.enter() and kept alive.
    All TTS requests are forwarded via httpx to the local HTTP server.
    The external .generate() method is a thin proxy that matches the old
    interface so callers don't need to change their code.
    """
 
    @modal.enter()
    def start_server(self):
        import time
        import httpx
 
        # Locate tools/api_server.py — fish_speech/tools are namespace pkgs (no __file__)
        import tools as _tools
        tools_dir = str(_tools.__path__[0])
        server_script = os.path.abspath(os.path.join(tools_dir, "api_server.py"))
 
        if not os.path.exists(server_script):
            raise RuntimeError(
                f"api_server.py not found at {server_script}. "
                "Ensure fish-speech is installed from GitHub source (not PyPI)."
            )

        # pyrootutils.setup_root() in api_server.py searches for .project-root.
        # Create it at site-packages level if missing (belt-and-suspenders).
        root_marker = os.path.join(os.path.dirname(tools_dir), ".project-root")
        if not os.path.exists(root_marker):
            open(root_marker, "w").close()
            print(f"[tts] Created missing .project-root at {root_marker}")

        cmd = [
            "python", server_script,
            "--llama-checkpoint-path", FISH_CHECKPOINT,
            "--decoder-checkpoint-path", FISH_CODEC_PATH,
            "--listen", f"0.0.0.0:{FISH_SERVER_PORT}",
        ]
        if USE_COMPILE:
            cmd.append("--compile")
 
        print(f"[tts] Starting api_server: {' '.join(cmd)}")
        self._server_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
 
        # Wait for the server to become healthy (up to 3 minutes for model load)
        base_url = f"http://127.0.0.1:{FISH_SERVER_PORT}"
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                r = httpx.get(f"{base_url}/v1/health", timeout=2)
                if r.status_code == 200:
                    print("[tts] api_server is healthy ✓")
                    self._base_url = base_url
                    return
            except Exception:
                pass
            time.sleep(2)
 
        # Dump server log on failure
        self._server_proc.kill()
        out, _ = self._server_proc.communicate()
        raise RuntimeError(
            f"[tts] api_server failed to start within 180s.\n"
            f"Server output:\n{out.decode(errors='replace')}"
        )
 
    @modal.exit()
    def stop_server(self):
        if hasattr(self, "_server_proc"):
            self._server_proc.terminate()
 
    @modal.method()
    def generate(
        self,
        text: str,
        voice_ref_id: Optional[str] = None,
        ref_audio_bytes: Optional[bytes] = None,
        ref_text: str = "",
        params: Optional[dict] = None,
    ) -> bytes:
        """
        Generate speech and return raw WAV bytes.

        Parameters
        ----------
        text            : Text to synthesize. Supports [tag] inline control.
        voice_ref_id    : ID of a pre-stored voice under /weights/voices/<id>.wav
        ref_audio_bytes : Raw WAV bytes of a reference speaker (zero-shot cloning)
        ref_text        : Transcript of ref_audio_bytes (improves clone quality)
        params          : Optional dict to override generation defaults:
                          top_p, temperature, repetition_penalty, max_new_tokens,
                          chunk_length, streaming (bool)
        """
        import base64
        import httpx

        params = params or {}

        # ── Resolve voice reference ──────────────────────────────────────────
        # Priority: explicit bytes > stored voice id > no reference (random timbre)
        if not ref_audio_bytes and voice_ref_id:
            audio_path = f"/weights/voices/{voice_ref_id}.wav"
            text_path  = f"/weights/voices/{voice_ref_id}.txt"
            if os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    ref_audio_bytes = f.read()
                if not ref_text and os.path.exists(text_path):
                    with open(text_path) as f:
                        ref_text = f.read().strip()
            else:
                print(f"[tts] Warning: voice '{voice_ref_id}' not found at {audio_path}")

        # ── Build ServeTTSRequest JSON body ──────────────────────────────────
        # api_server v2.0 uses MessagePack + JSON body, not multipart.
        # Ref audio is base64-encoded and embedded in the JSON payload.
        payload: dict = {
            "text": text,
            "format": params.get("format", "wav"),
            "streaming": params.get("streaming", False),
            "top_p": params.get("top_p", 0.7),
            "temperature": params.get("temperature", 0.7),
            "repetition_penalty": params.get("repetition_penalty", 1.2),
            "max_new_tokens": params.get("max_new_tokens", 1024),
            "chunk_length": params.get("chunk_length", 300),
        }

        if ref_audio_bytes:
            payload["references"] = [
                {
                    "audio": base64.b64encode(ref_audio_bytes).decode("ascii"),
                    "text": ref_text,
                }
            ]

        response = httpx.post(
            f"{self._base_url}/v1/tts",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()

        wav_bytes = response.content
        # Log approximate duration
        import struct
        try:
            # Read sample rate (bytes 24-27) and data chunk size from WAV header
            sr   = struct.unpack_from("<I", wav_bytes, 24)[0]
            size = struct.unpack_from("<I", wav_bytes, 40)[0]
            duration = size / (sr * 2)  # 16-bit mono
            print(f"[tts] Generated {duration:.2f}s of audio ({len(wav_bytes)//1024} KB)")
        except Exception:
            print(f"[tts] Generated {len(wav_bytes)//1024} KB of audio")

        return wav_bytes
 
    @modal.method()
    def encode_reference(self, audio_bytes: bytes) -> bytes:
        """
        Encode a WAV reference into VQ codes (.npy bytes) via POST /v1/vqgan/encode.
        Useful for caching reference encodings to avoid re-encoding on every call.
        """
        import httpx
        response = httpx.post(
            f"{self._base_url}/v1/vqgan/encode",
            files={"audio": ("ref.wav", audio_bytes, "audio/wav")},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.content  # raw .npy bytes
 

# ─── 3. Embeddings — SentenceTransformers ────────────────────────────────────

@app.cls(
    image=base_image,
    gpu=None,                  # CPU is fine for embedding extraction
    volumes={"/weights": weights_volume},
    scaledown_window=300,
)
class Embeddings:
    @modal.enter()
    def load_model(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            device="cpu",
            cache_folder="/weights/embeddings",
        )

    @modal.method()
    def get_embedding(self, text: str) -> List[float]:
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()


# ─── 4. Weight Downloader (Run Once) ──────────────────────────────────────────

@app.function(image=base_image, volumes={"/weights": weights_volume})
def setup():
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer
    print("Downloading weights...")
    snapshot_download(repo_id="systran/faster-whisper-medium.en", local_dir="/weights/whisper")
    snapshot_download(repo_id="fishaudio/s2-pro", local_dir="/weights/s2-pro")
    SentenceTransformer("all-MiniLM-L6-v2", cache_folder="/weights/embeddings")
    weights_volume.commit()
    print("✅ Setup complete.")