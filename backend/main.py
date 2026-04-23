import json
import asyncio
import hashlib
import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Any

# Core imports
from core.agents.orchestrator import handle_message
from core.agents.persona import persona_stream, get_greeting, get_focus_enter, get_focus_exit
from perception.manager import SensesManager
from memory.memory_manager import memory_manager

# Modal Service Integration
from core.modal.modal_handler import get_modal_client, tts_gpu_async
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
CACHE_DIR = Path("static/tts_cache")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ─── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self.queue: list[dict] = []  # buffer events if frontend disconnects

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"[ws] frontend connected — {len(self.active)} active")

        # flush queued events
        for event in self.queue:
            await ws.send_text(json.dumps(event))
        self.queue.clear()

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        print(f"[ws] frontend disconnected — {len(self.active)} active")

    async def emit(self, event: dict):
        if not self.active:
            print(f"[ws] no frontend — queuing event: {event}")
            self.queue.append(event)
            return
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def emit_state(self, state: str):
        await self.emit({ "type": "STATE_CHANGE", "state": state })

    async def emit_speech(self, text: str, audio_url: str = ""):
        await self.emit({ "type": "SPEECH", "text": text, "audio_url": audio_url })

    async def emit_alert(self, title: str, source: str = ""):
        await self.emit({ "type": "ALERT", "title": title, "source": source })


manager = ConnectionManager()


# ─── TTS Helper ────────────────────────────────────────────────────────────────

async def speak_tts(text: str) -> str:
    """
    Generates TTS using FishSpeech S2 on Modal GPU.
    Caches the result locally to save GPU credits on repeat phrases.
    """
    if not text: return ""
    
    # 1. Check Cache First
    cache_key = hashlib.md5(text.encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.wav"
    audio_url = f"http://localhost:8000/static/tts_cache/{cache_key}.wav"

    if cache_path.exists():
        return audio_url
    is_modal_enabled = get_modal_client().health_check()
    # 2. Generate via Modal GPU
    if is_modal_enabled == True:
        print(f"[tts] Requesting GPU synthesis for: {text[:30]}...")
        try:
            audio_bytes = await tts_gpu_async(text)
            if audio_bytes:
                # Write to disk in a separate thread
                await asyncio.to_thread(cache_path.write_bytes, audio_bytes)
                return audio_url
        except Exception as e:
            print(f"[tts] Modal GPU failed, falling back: {e}")

# ─── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            event = json.loads(data)
            print(f"[ws] from frontend: {event}")
            await handle_frontend_event(event)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        print(f"[ws] error: {e}")
        manager.disconnect(ws)


async def handle_frontend_event(event: dict):
    if event.get("type") == "USER_MESSAGE":
        text = event.get("text", "")
        if not text:
            return

        # tell frontend she's thinking
        await manager.emit({ "type": "TASK_START" })

        # run through orchestrator
        result = await handle_message(text)

        # send speech back to frontend
        await manager.emit_speech(
            result["speech_text"],
            result.get("audio_url", "")
        )


@app.post("/message")
async def send_message(text: str, app_context: str = ""):
    await manager.emit({ "type": "WAKE" })
    await asyncio.sleep(0.1)
    await manager.emit({ "type": "TASK_START" })

    context = {}
    if app_context:
        context["active_app"] = app_context

    full_text = ""
    async for chunk in persona_stream(text, context):
        full_text += chunk
        await manager.emit({
            "type": "SPEECH_CHUNK",
            "chunk": chunk,
            "text": full_text,
        })

    # generate TTS in parallel with text streaming
    audio_url = await speak_tts(full_text)

    # send final speech event with audio
    await manager.emit_speech(full_text, audio_url)
    return { "ok": True }


@app.post("/focus")
async def focus_mode(entering: bool = True):
    if entering:
        text = get_focus_enter()
        await manager.emit({ "type": "FOCUS_MODE" })
    else:
        text = get_focus_exit()
        await manager.emit({ "type": "FOCUS_END" })

    await manager.emit_speech(text)
    return { "ok": True }


# ─── Voice Management (FishSpeech S2 Zero-Shot Voice Cloning) ────────────────

@app.post("/voice/upload")
async def upload_voice(
    reference_id: str = Form(...), 
    transcription: str = Form(""),
    file: UploadFile = File(...)
):
    """Updates the 'main_voice.wav' in the system (requires Modal volume sync)."""
    try:
        # In a real setup, you'd save this locally and then 
        # use modal.Volume.put via a subprocess or utility
        content = await file.read()
        local_path = Path(f"static/voices/{reference_id}.wav")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        
        return {"success": True, "message": f"Voice {reference_id} saved locally."}
    except Exception as e:
        return {"success": False, "message": str(e)}

async def startup():
    asyncio.create_task(heartbeat())
    asyncio.create_task(startup_greeting())
    print("[backend] started")


async def startup_greeting():
    # wait for frontend to connect
    await asyncio.sleep(3)
    text = get_greeting()
    audio_url = await speak_tts(text)
    await manager.emit({ "type": "WAKE" })
    await asyncio.sleep(0.2)
    await manager.emit_speech(text, audio_url)
# ─── Heartbeat ────────────────────────────────────────────────────────────────

async def heartbeat():
    while True:
        await asyncio.sleep(30)
        await manager.emit({ "type": "PING" })

@app.on_event("startup")
async def startup():
    asyncio.create_task(heartbeat())
    print("[backend] started")


# ─── Dev endpoints ────────────────────────────────────────────────────────────

class EventBody(BaseModel):
    type: str
    model_config = { "extra": "allow" }

@app.post("/send")
async def send_event(event: EventBody):
    payload = event.model_dump()
    print(f"[send] {payload}")
    await manager.emit(payload)
    return { "ok": True }

@app.post("/speak")
async def speak(text: str, audio_url: str = ""):
    await manager.emit_speech(text, audio_url)
    return { "ok": True }


senses: SensesManager = None
@app.on_event("startup")
async def startup():
    global senses
    client = get_modal_client()
    # Print GPU status on startup
    print("\n" + "="*60)
    print("WAIF Backend Startup - GPU Processing Check")
    print("="*60)
    gpu_status = "READY" if client.health_check() else "DISABLED"
    print(f"\n🚀 WAIF Startup | GPU Status: {gpu_status}")
    asyncio.create_task(heartbeat())
    asyncio.create_task(startup_greeting())

    loop = asyncio.get_event_loop()

    senses = SensesManager(
        on_wake=handle_wake,
        on_transcription=handle_transcription,
        on_app_change=handle_app_change,
    )
    senses.start(loop)
    print("[backend] started")


async def handle_wake():
    print("[senses] wake detected")
    await manager.emit({ "type": "WAKE" })


async def handle_transcription(text: str):
    print(f"[senses] transcription: {text}")
    context = senses.get_context() if senses else {}

    await manager.emit({ "type": "TASK_START" })

    full_text = ""
    async for chunk in persona_stream(text, context):
        full_text += chunk
        await manager.emit({
            "type": "SPEECH_CHUNK",
            "chunk": chunk,
            "text": full_text,
        })

    audio_url = await speak_tts(full_text)
    await manager.emit_speech(full_text, audio_url)


async def handle_app_change(app_name: str):
    print(f"[senses] app changed: {app_name}")
    await manager.emit({
        "type": "HUD_UPDATE",
        "active_app": app_name,
    })

    # auto focus dim when certain apps are active
    focus_apps = ["code", "cursor", "vim", "nvim", "pycharm", "webstorm"]
    if any(f in app_name.lower() for f in focus_apps):
        await manager.emit({ "type": "FOCUS_MODE" })
    else:
        await manager.emit({ "type": "FOCUS_END" })



@app.get("/memory/recall")
async def recall_memory(query: str):
    result = await memory_manager.recall(query)
    return { "result": result }

@app.get("/memory/week")
async def recall_week():
    result = await memory_manager.recall_week()
    return { "result": result }

@app.post("/memory/fact")
async def store_fact(fact: str):
    await memory_manager.remember_fact(fact)
    return { "ok": True }
