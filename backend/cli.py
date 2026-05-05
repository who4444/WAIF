#!/usr/bin/env python3
"""Terminal CLI for testing LLM responses directly."""

import argparse
import asyncio
import io
import sys
import tempfile
from pathlib import Path

from core.llm_client import llm_complete, llm_stream
from core.agents.persona import SYSTEM_PROMPT
from core.modal.modal_handler import tts_gpu_async, get_modal_client


async def run(
    message: str,
    mode: str = "persona",
    system: str = "",
    max_tokens: int = 512,
    stream: bool = False,
    tts: bool = False,
    tts_output: str = "",
):
    messages = [{"role": "user", "content": message}]

    response = ""
    if stream:
        async for chunk in llm_stream(messages, system=system, mode=mode, max_tokens=max_tokens):
            print(chunk, end="", flush=True)
            response += chunk
        print()
    else:
        response = await llm_complete(messages, system=system, mode=mode, max_tokens=max_tokens)
        print(response)

    if tts and response:
        await speak(response, tts_output)


async def speak(text: str, output_path: str = ""):
    print("\n[tts] generating speech...", end=" ", flush=True)
    try:
        audio_bytes = await tts_gpu_async(text)
        if not audio_bytes:
            print("failed — Modal GPU unavailable.")
            return

        if output_path:
            Path(output_path).write_bytes(audio_bytes)
            print(f"saved to {output_path}")

        _play_audio(audio_bytes)
    except Exception as e:
        print(f"failed: {e}")


def _play_audio(data: bytes):
    try:
        import simpleaudio as sa
        wave = sa.WaveObject.from_wave_file(io.BytesIO(data))
        play = wave.play()
        print("speaking~")
        play.wait_done()
    except ImportError:
        # fallback: write to temp file, use system player
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(data)
            tmp = f.name
        print(f"playing via system...")
        import subprocess
        subprocess.run(["aplay", tmp], check=False)
        Path(tmp).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Send a prompt to the LLM from the terminal.")
    parser.add_argument(
        "message", nargs="*", help="Message to send. Reads from stdin if omitted."
    )
    parser.add_argument(
        "--mode", choices=["persona", "reasoning"], default="persona",
        help="LLM mode: persona (Qwen) or reasoning (DeepSeek). Default: persona",
    )
    parser.add_argument(
        "--system", default=None,
        help="Custom system prompt. Persona mode defaults to Leiwen persona if not set.",
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Send with no system prompt (overrides persona default).",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=512, help="Max tokens in response. Default: 512"
    )
    parser.add_argument(
        "--stream", action="store_true", help="Stream the response token by token."
    )
    parser.add_argument(
        "--tts", action="store_true", help="Speak the response aloud after printing."
    )
    parser.add_argument(
        "--tts-output", default="", help="Save TTS audio to WAV file path."
    )

    args = parser.parse_args()

    if args.message:
        message = " ".join(args.message)
    elif not sys.stdin.isatty():
        message = sys.stdin.read().strip()
    else:
        parser.print_help()
        sys.exit(1)

    if not message:
        print("Error: empty message.", file=sys.stderr)
        sys.exit(1)

    # Resolve system prompt
    if args.raw:
        system = ""
    elif args.system is not None:
        system = args.system
    elif args.mode == "persona":
        system = SYSTEM_PROMPT
    else:
        system = ""

    asyncio.run(run(
        message=message,
        mode=args.mode,
        system=system,
        max_tokens=args.max_tokens,
        stream=args.stream,
        tts=args.tts or bool(args.tts_output),
        tts_output=args.tts_output,
    ))


if __name__ == "__main__":
    main()
