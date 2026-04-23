"""
Modal integration for GPU-accelerated tasks (STT, TTS, Embeddings).
Optimized for @app.cls usage to ensure low-latency 'warm' container access.
"""

import asyncio
import io
import os
from typing import Optional, List
from config import MODAL_ENABLED

# Configuration - must match your deployed Modal App name
MODAL_APP_NAME = "waif-gpu-service"

class ModalClient:
    """Singleton Client for interacting with persistent Modal GPU Services."""
    
    def __init__(self):
        self.enabled = MODAL_ENABLED
        self._initialized = False
        
        # Service placeholders
        self._stt_service = None
        self._tts_service = None
        self._embed_service = None

    def _lazy_init(self):
        """Connects to the remote Modal classes if not already initialized."""
        if not self.enabled or self._initialized:
            return

        try:
            import modal
            print(f"[modal] Connecting to remote services in '{MODAL_APP_NAME}'...")
            
            # Lookup the Classes (this does not trigger a cold start yet)
            stt_cls = modal.Cls.from_name(MODAL_APP_NAME, "WhisperSTT")
            tts_cls = modal.Cls.from_name(MODAL_APP_NAME, "FishSpeechTTS")
            embed_cls = modal.Cls.from_name(MODAL_APP_NAME, "Embeddings")

            # Instantiate the service handles
            self._stt_service = stt_cls()
            self._tts_service = tts_cls()
            self._embed_service = embed_cls()
            
            self._initialized = True
            print("[modal] GPU Services linked and ready.")
        except Exception as e:
            print(f"[modal] Initialization failed: {e}")
            self.enabled = False

    def health_check(self) -> bool:
        if not self.enabled: return False
        self._lazy_init()
        return self._initialized

    # ─── TTS: FishSpeech S2 ───────────────────────────────────────────────────

    def generate_speech(self, text: str) -> Optional[bytes]:
        """Offloads high-quality TTS to Modal A10G GPU."""
        if not self.health_check(): return None
        
        try:
            result = self._tts_service.generate.remote(text)
            return result
        except Exception as e:
            print(f"[modal] TTS Error: {e}")
            return None

    # ─── STT: Faster-Whisper ──────────────────────────────────────────────────

    def transcribe_audio(self, audio_bytes: bytes) -> Optional[str]:
        """Offloads transcription to Modal T4 GPU."""
        if not self.health_check(): return None
        
        try:
            result = self._stt_service.transcribe.remote(audio_bytes)
            return result
        except Exception as e:
            print(f"[modal] STT Error: {e}")
            return None

    # ─── Embeddings: SentenceTransformers ─────────────────────────────────────

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generates semantic vectors for RAG/Memory."""
        if not self.health_check(): return None
        
        try:
            return self._embed_service.get_embedding.remote(text)
        except Exception as e:
            print(f"[modal] Embedding Error: {e}")
            return None


# ─── Global Singleton ─────────────────────────────────────────────────────────

_client_instance: Optional[ModalClient] = None

def get_modal_client() -> ModalClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = ModalClient()
    return _client_instance

# ─── Async Wrappers (Thread-safe) ─────────────────────────────────────────────

async def tts_gpu_async(text: str) -> Optional[bytes]:
    """Async TTS: Sends text to GPU and receives WAV bytes."""
    client = get_modal_client()
    return await asyncio.to_thread(client.generate_speech, text)

async def transcribe_gpu_async(audio_bytes: bytes) -> Optional[str]:
    """Async STT: Sends audio bytes to GPU and receives text."""
    client = get_modal_client()
    return await asyncio.to_thread(client.transcribe_audio, audio_bytes)

async def embedding_gpu_async(text: str) -> Optional[List[float]]:
    """Async Embedding: Returns a 384-dim vector."""
    client = get_modal_client()
    return await asyncio.to_thread(client.get_embedding, text)