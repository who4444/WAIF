import asyncio
from screen import ScreenWatcher, get_screen_context
from audio import AudioListener

class SensesManager:
    def __init__(self, on_wake, on_transcription, on_app_change):
        self.on_wake = on_wake
        self.on_transcription = on_transcription
        self.on_app_change = on_app_change
        self.screen_watcher = ScreenWatcher(on_change=on_app_change)
        self.audio_listener = AudioListener(
            on_wake=on_wake,
            on_transcription=on_transcription,
        )
        self.current_context = {}

    def start(self, loop):
        self.audio_listener.set_loop(loop)
        self.audio_listener.start()
        asyncio.create_task(self.screen_watcher.start())
        print("[senses] all senses active")

    def get_context(self) -> dict:
        return get_screen_context()

    def stop(self):
        self.audio_listener.stop()
        self.screen_watcher.stop()