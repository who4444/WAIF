import asyncio
import hashlib
import os
from pathlib import Path
from elevenlabs import AsyncElevenLabs
from config import ELEVENLABS_API_KEY

# ─── Client ───────────────────────────────────────────────────────────────────

client = AsyncElevenLabs(api_key=ELEVENLABS_API_KEY)

# ─── Config ───────────────────────────────────────────────────────────────────

VOICE_ID = "your_voice_id_here"  # replace with your chosen voice
MODEL_ID = "eleven_turbo_v2_5"   # fastest model, lowest latency
CACHE_DIR = Path("static/tts_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─── Cache ────────────────────────────────────────────────────────────────────

def cache_path(text: str) -> Path:
    key = hashlib.md5(text.encode()).hexdigest()
    return CACHE_DIR / f"{key}.mp3"


def is_cached(text: str) -> bool:
    return cache_path(text).exists()


def get_cache_url(text: str) -> str:
    key = hashlib.md5(text.encode()).hexdigest()
    return f"http://localhost:8000/static/tts_cache/{key}.mp3"


# ─── Generate ─────────────────────────────────────────────────────────────────

async def generate_tts(text: str) -> str:
    """Generate TTS audio, return URL to the file."""

    # return cached version if available
    if is_cached(text):
        print(f"[tts] cache hit: {text[:40]}")
        return get_cache_url(text)

    print(f"[tts] generating: {text[:40]}")

    try:
        audio = await client.generate(
            text=text,
            voice=VOICE_ID,
            model=MODEL_ID,
        )

        # collect all chunks
        chunks = []
        async for chunk in audio:
            chunks.append(chunk)

        audio_bytes = b"".join(chunks)

        # save to cache
        path = cache_path(text)
        path.write_bytes(audio_bytes)
        print(f"[tts] saved: {path}")

        return get_cache_url(text)

    except Exception as e:
        print(f"[tts] error: {e}")
        return ""


async def generate_tts_streaming(text: str):
    """Stream audio chunks directly — lower latency than waiting for full file."""
    try:
        audio_stream = await client.generate(
            text=text,
            voice=VOICE_ID,
            model=MODEL_ID,
            stream=True,
        )
        async for chunk in audio_stream:
            yield chunk
    except Exception as e:
        print(f"[tts stream] error: {e}")