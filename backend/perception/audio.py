import asyncio
import threading
import numpy as np

# ─── Config ───────────────────────────────────────────────────────────────────

WAKE_WORD = "hey dear"
WAKE_WORDS = [WAKE_WORD, "hey leiwen", "leiwen"]

# Set this to True to use Modal's GPU for transcription
MODAL_ENABLED = True 
MODAL_APP_NAME = "waif-gpu-service" 

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
            import modal
            try:
                # Lookup the remote function (Class.method format)
                self.modal_transcribe = modal.Cls.from_name(
                    MODAL_APP_NAME, "WhisperTTS.transcribe"
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
        try:
            from RealtimeSTT import AudioToTextRecorder
        except ImportError:
            print("[audio] ERROR: RealtimeSTT not installed.")
            return
        
        # We use a tiny model locally just for VAD/Fast feedback.
        # The heavy lifting will happen on the Modal GPU.
        self.recorder = AudioToTextRecorder(
            spinner=False,
            model="tiny.en",          
            language="en",
            device="cpu",              # Local processing on CPU
            wakeword_backend="oww",
            wake_words=",".join(WAKE_WORDS),
            on_wakeword_detected=self._on_wake_detected,
            silero_sensitivity=0.5,
            post_speech_silence_duration=0.6, # Slightly longer for Modal latency buffer
            min_length_of_recording=0.5,
        )

        print(f"[audio] listening for wake word: {WAKE_WORDS}")

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