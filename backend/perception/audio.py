import asyncio
import os
import threading
import time
import numpy as np

# ─── Config ───────────────────────────────────────────────────────────────────

BUILT_IN_OPENWAKEWORD_MODELS = {
    "alexa",
    "hey_mycroft",
    "hey_jarvis",
    "timer",
    "weather",
}


def _csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# openWakeWord cannot detect arbitrary text phrases unless a matching custom
# model is provided. The bundled model that maps closest to a companion wake
# phrase is "hey_jarvis".
WAKE_WORDS = _csv_env("WAIF_WAKE_WORDS", "hey_jarvis")
OPENWAKEWORD_MODEL_PATHS = os.getenv("WAIF_OPENWAKEWORD_MODEL_PATHS", "").strip()

# Set this to True to use Modal's GPU for transcription
MODAL_ENABLED = _bool_env("WAIF_MODAL_STT_ENABLED", True)
MODAL_APP_NAME = os.getenv("WAIF_MODAL_APP_NAME", "waif-gpu-service")

# ─── Audio listener ───────────────────────────────────────────────────────────

class AudioListener:
    def __init__(self, on_wake, on_transcription):
        self.on_wake = on_wake
        self.on_transcription = on_transcription
        self.recorder = None
        self.listening_for_command = False
        self.thread = None
        self.running = False
        self._loop = None
        
        # Modal setup
        self.modal_transcribe = None
        if MODAL_ENABLED:
            try:
                import modal
                # Lookup the remote function (Class.method format)
                self.modal_transcribe = modal.Cls.from_name(
                    MODAL_APP_NAME, "WhisperSTT.transcribe"
                )
                print("[modal] remote function linked")
            except Exception as e:
                print(f"[modal] ERROR: Could not link remote function: {e}")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[audio] listener started")

    def stop(self):
        self.running = False
        if self.recorder:
            self.recorder.stop()

    def _run(self):
        # openwakeword >=0.4.0 bundles models in the package and removed
        # download_models(), but RealtimeSTT 0.3.104 still calls it. Patch it.
        # Also, openwakeword 0.4.0 AudioFeatures doesn't accept inference_framework
        # kwarg (added in 0.5.0), but RealtimeSTT passes it through Model -> AudioFeatures.
        try:
            import openwakeword.utils as owu
            if not hasattr(owu, "download_models"):
                owu.download_models = lambda: None

            _orig_af_init = owu.AudioFeatures.__init__
            def _patched_af_init(self, *args, **kwargs):
                kwargs.pop("inference_framework", None)
                _orig_af_init(self, *args, **kwargs)
            owu.AudioFeatures.__init__ = _patched_af_init
        except ImportError:
            pass

        try:
            from RealtimeSTT import AudioToTextRecorder
        except ImportError:
            print("[audio] ERROR: RealtimeSTT not installed.")
            return

        unsupported_words = [
            word for word in WAKE_WORDS
            if word.lower().replace(" ", "_") not in BUILT_IN_OPENWAKEWORD_MODELS
        ]
        if unsupported_words and not OPENWAKEWORD_MODEL_PATHS:
            print(
                "[audio] WARNING: openWakeWord cannot detect arbitrary wake "
                f"phrases without custom model files: {unsupported_words}. "
                "Using bundled models instead. Say one of: "
                f"{sorted(BUILT_IN_OPENWAKEWORD_MODELS)}"
            )
        
        # We use a tiny model locally just for VAD/Fast feedback.
        # The heavy lifting will happen on the Modal GPU.
        try:
            self.recorder = AudioToTextRecorder(
                spinner=False,
                model="tiny.en",
                language="en",
                device="cpu",              # Local processing on CPU
                wakeword_backend="oww",
                wake_words=",".join(WAKE_WORDS),
                openwakeword_model_paths=OPENWAKEWORD_MODEL_PATHS or None,
                on_wakeword_detected=self._on_wake_detected,
                silero_sensitivity=0.5,
                post_speech_silence_duration=0.6, # Slightly longer for Modal latency buffer
                min_length_of_recording=0.5,
            )
        except Exception as e:
            print(f"[audio] ERROR: could not initialize microphone recorder: {e}")
            print("[audio] Check microphone permissions, audio device access, and RealtimeSTT dependencies.")
            return

        if OPENWAKEWORD_MODEL_PATHS:
            print(f"[audio] listening with custom openWakeWord model(s): {OPENWAKEWORD_MODEL_PATHS}")
        else:
            print(f"[audio] listening for bundled openWakeWord model(s): {sorted(BUILT_IN_OPENWAKEWORD_MODELS)}")
            print(f"[audio] configured wake phrase hint: {WAKE_WORDS}")

        while self.running:
            try:
                if self.listening_for_command:
                    # 1. This blocks until speech finishes.
                    # It transcribes locally with 'tiny.en' first.
                    local_text = self.recorder.text()
                    
                    if local_text and local_text.strip():
                        print(f"[audio] local (tiny) preview: {local_text}")
                        
                        final_text = local_text
                        
                        # 2. If Modal is enabled, get raw audio and send to GPU
                        if MODAL_ENABLED and self.modal_transcribe:
                            print("[audio] fetching high-res transcription from Modal GPU...")
                            # get_last_recording() returns a float32 numpy array
                            audio_data = self.recorder.get_last_recording()
                            
                            # Send bytes to Modal (A10G/L4/etc.)
                            # This is a blocking network call inside this thread
                            final_text = self.modal_transcribe.remote(audio_data.tobytes())
                            print(f"[audio] modal (medium) result: {final_text}")

                        self.listening_for_command = False
                        
                        # 3. Fire callback in main event loop
                        asyncio.run_coroutine_threadsafe(
                            self.on_transcription(final_text.strip()),
                            self._loop
                        )
                else:
                    time.sleep(0.05)
            except Exception as e:
                print(f"[audio] error in loop: {e}")

    def _on_wake_detected(self):
        print("[audio] wake word detected!")
        self.listening_for_command = True
        asyncio.run_coroutine_threadsafe(
            self.on_wake(),
            self._loop
        )

    def set_loop(self, loop):
        self._loop = loop
