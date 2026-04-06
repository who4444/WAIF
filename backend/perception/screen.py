import asyncio
from datetime import datetime

# ─── Active window ────────────────────────────────────────────────────────────

def get_active_app() -> str:
    try:
        import sys
        if sys.platform == "win32":
            return _get_active_app_windows()
        elif sys.platform == "darwin":
            return _get_active_app_macos()
        else:
            return _get_active_app_linux()
    except Exception as e:
        print(f"[screen] error getting active app: {e}")
        return ""


def _get_active_app_linux() -> str:
    import subprocess
    try:
        result = subprocess.check_output(
            ["xdotool", "getactivewindow", "getwindowname"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return result
    except Exception:
        return ""


# ─── Context builder ──────────────────────────────────────────────────────────

def get_screen_context() -> dict:
    return {
        "active_app": get_active_app(),
        "time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%A, %B %d"),
    }


# ─── Watcher — polls every 3 seconds ─────────────────────────────────────────

class ScreenWatcher:
    def __init__(self, on_change):
        self.on_change = on_change
        self.last_app = ""
        self.running = False

    async def start(self):
        self.running = True
        print("[screen] watcher started")
        while self.running:
            app = get_active_app()
            if app and app != self.last_app:
                self.last_app = app
                print(f"[screen] active app: {app}")
                await self.on_change(app)
            await asyncio.sleep(3)

    def stop(self):
        self.running = False