import modal
import io


class TTSService:
    def __init__(self):
        self.tts_remote = modal.Function.from_name("waif-gpu-service", "FishSpeechTTS.generate")
    
    async def generate_tts(self,text: str) -> str:
        """Generate TTS audio, return URL to the file."""
        print(f"[tts] generating audio for: {text}")
        audio_bytes = self.tts_remote.remote(text)
        # Play audio using your local player (pydub, simpleaudio, etc.)
        self._play_audio(audio_bytes)

    def _play_audio(self, data):
        import simpleaudio as sa
        wave_obj = sa.WaveObject.from_wave_file(io.BytesIO(data))
        wave_obj.play().wait_done()