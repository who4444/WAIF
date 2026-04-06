import asyncio
import threading
from RealtimeSTT import AudioToTextRecorder

# ─── Config ───────────────────────────────────────────────────────────────────

WAKE_WORD = "dear"
WAKE_WORDS = [WAKE_WORD, "hey leiwen", "leiwen"]

# ─── Audio listener ───────────────────────────────────────────────────────────

class AudioListener:
    def __init__(self, on_wake, on_transcription):
        self.on_wake = on_wake
        self.on_transcription = on_transcription
        self.recorder = None
        self.listening_for_command = False
        self.thread = None
        self.running = False

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
        self.recorder = AudioToTextRecorder(
            spinner=False,
            model="tiny.en",          # fast, lightweight
            language="en",
            wake_words=",".join(WAKE_WORDS),
            wake_word_activation_delay=0.5,
            on_wakeword_detected=self._on_wake_detected,
            silero_sensitivity=0.5,
            webrtc_sensitivity=3,
            post_speech_silence_duration=0.4,
            min_length_of_recording=0.3,
        )

        print(f"[audio] listening for wake word: {WAKE_WORDS}")

        while self.running:
            try:
                if self.listening_for_command:
                    text = self.recorder.text()
                    if text and text.strip():
                        print(f"[audio] transcribed: {text}")
                        self.listening_for_command = False
                        # fire callback in event loop
                        asyncio.run_coroutine_threadsafe(
                            self.on_transcription(text.strip()),
                            self._loop
                        )
            except Exception as e:
                print(f"[audio] error: {e}")

    def _on_wake_detected(self):
        print("[audio] wake word detected!")
        self.listening_for_command = True
        asyncio.run_coroutine_threadsafe(
            self.on_wake(),
            self._loop
        )

    def set_loop(self, loop):
        self._loop = loop