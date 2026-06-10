import json
import asyncio
import hashlib
import re
from pathlib import Path
from fastapi import Depends, FastAPI, Header, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, AsyncGenerator
import json as json_module

# Core imports
from core.agents.orchestrator import handle_message
from core.agents.persona import get_greeting, get_focus_enter, get_focus_exit, SYSTEM_PROMPT
from core.llm_client import llm_complete, llm_stream
from perception.manager import SensesManager
from memory.memory_manager import memory_manager
from config import WAIF_ALLOWED_ORIGINS, WAIF_API_KEY, WAIF_SENSES_ENABLED

# Modal Service Integration
from core.modal.modal_handler import get_modal_client, tts_gpu_async
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=WAIF_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
BACKEND_ROOT = Path(__file__).resolve().parent
STATIC_DIR = BACKEND_ROOT / "static"
CACHE_DIR = STATIC_DIR / "tts_cache"
VOICE_DIR = STATIC_DIR / "voices"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    return origin in WAIF_ALLOWED_ORIGINS


async def require_api_key(x_waif_api_key: str | None = Header(default=None)):
    if WAIF_API_KEY and x_waif_api_key != WAIF_API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")


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
senses: SensesManager | None = None
background_tasks: list[asyncio.Task] = []


# ─── TTS Helper ────────────────────────────────────────────────────────────────

async def speak_tts(text: str) -> str:
    """
    Generates TTS using FishSpeech S2 on Modal GPU.
    Caches the result locally to save GPU credits on repeat phrases.
    """
    if not text:
        return ""
    
    # 1. Check Cache First
    cache_key = hashlib.md5(text.encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.wav"
    audio_url = f"/static/tts_cache/{cache_key}.wav"

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
    return ""

# ─── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if not _origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    ws_key = ws.headers.get("x-waif-api-key") or ws.query_params.get("api_key")
    if WAIF_API_KEY and ws_key != WAIF_API_KEY:
        await ws.close(code=1008)
        return
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
        audio_url = result.get("audio_url") or await speak_tts(result["speech_text"])

        # send speech back to frontend
        await manager.emit_speech(
            result["speech_text"],
            audio_url,
        )


@app.post("/message")
async def send_message(text: str, app_context: str = "", _: None = Depends(require_api_key)):
    await manager.emit({ "type": "WAKE" })
    await asyncio.sleep(0.1)
    await manager.emit({ "type": "TASK_START" })

    context = {}
    if app_context:
        context["active_app"] = app_context

    result = await handle_message(text, context)
    full_text = result["speech_text"]
    audio_url = result.get("audio_url") or await speak_tts(full_text)

    # send final speech event with audio
    await manager.emit_speech(full_text, audio_url)
    return { "ok": True }


@app.post("/focus")
async def focus_mode(entering: bool = True, _: None = Depends(require_api_key)):
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
    file: UploadFile = File(...),
    _: None = Depends(require_api_key),
):
    """Updates the 'main_voice.wav' in the system (requires Modal volume sync)."""
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", reference_id):
            raise HTTPException(
                status_code=400,
                detail="reference_id must be 1-64 chars: letters, numbers, underscore, hyphen",
            )
        if file.content_type and not file.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="voice upload must be an audio file")

        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="voice upload is too large")

        local_path = (VOICE_DIR / f"{reference_id}.wav").resolve()
        if VOICE_DIR.resolve() not in local_path.parents:
            raise HTTPException(status_code=400, detail="invalid reference path")
        await asyncio.to_thread(local_path.write_bytes, content)

        if transcription:
            text_path = VOICE_DIR / f"{reference_id}.txt"
            await asyncio.to_thread(text_path.write_text, transcription)
        
        return {"success": True, "message": f"Voice {reference_id} saved locally."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


# ─── Dev endpoints ────────────────────────────────────────────────────────────

class EventBody(BaseModel):
    type: str
    model_config = { "extra": "allow" }

@app.post("/send")
async def send_event(event: EventBody, _: None = Depends(require_api_key)):
    payload = event.model_dump()
    print(f"[send] {payload}")
    await manager.emit(payload)
    return { "ok": True }

@app.post("/speak")
async def speak(text: str, audio_url: str = "", _: None = Depends(require_api_key)):
    await manager.emit_speech(text, audio_url)
    return { "ok": True }


# ─── Prompt endpoints (direct LLM access, no persona pipeline) ─────────────

class PromptBody(BaseModel):
    message: str
    mode: str = "persona"        # persona | reasoning
    system: Optional[str] = None # None = auto: persona mode uses Leiwen prompt
    max_tokens: int = 512

@app.post("/prompt")
async def prompt(body: PromptBody, _: None = Depends(require_api_key)):
    """Direct LLM call. Returns raw response — no conversation history, no TTS."""
    system = body.system
    if system is None and body.mode == "persona":
        system = SYSTEM_PROMPT
    elif system is None:
        system = ""

    messages = [{"role": "user", "content": body.message}]
    response = await llm_complete(
        messages=messages,
        system=system,
        mode=body.mode,
        max_tokens=body.max_tokens,
    )
    return {"response": response, "mode": body.mode}


@app.post("/prompt/stream")
async def prompt_stream(body: PromptBody, _: None = Depends(require_api_key)):
    """Streaming direct LLM call. Returns newline-delimited JSON chunks."""
    system = body.system
    if system is None and body.mode == "persona":
        system = SYSTEM_PROMPT
    elif system is None:
        system = ""

    messages = [{"role": "user", "content": body.message}]
    async def generate() -> AsyncGenerator[str, None]:
        chunks: list[str] = []
        async for chunk in llm_stream(
            messages=messages,
            system=system,
            mode=body.mode,
            max_tokens=body.max_tokens,
        ):
            chunks.append(chunk)
            yield json_module.dumps({"chunk": chunk}) + "\n"
        full_response = "".join(chunks)
        audio_url = await speak_tts(full_response)
        await manager.emit_speech(full_response, audio_url)
        yield json_module.dumps({"done": True, "response": full_response}) + "\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.on_event("startup")
async def startup_event():
    global senses
    client = get_modal_client()
    # Print GPU status on startup
    print("\n" + "="*60)
    print("WAIF Backend Startup - GPU Processing Check")
    print("="*60)
    gpu_status = "READY" if client.health_check() else "DISABLED"
    print(f"\nWAIF Startup | GPU Status: {gpu_status}")
    background_tasks.append(asyncio.create_task(heartbeat()))
    background_tasks.append(asyncio.create_task(startup_greeting()))

    loop = asyncio.get_event_loop()

    if WAIF_SENSES_ENABLED:
        senses = SensesManager(
            on_wake=handle_wake,
            on_transcription=handle_transcription,
            on_app_change=handle_app_change,
        )
        senses.start(loop)
    else:
        print("[senses] disabled by WAIF_SENSES_ENABLED=false")
    print("[backend] started")


@app.on_event("shutdown")
async def shutdown_event():
    if senses:
        senses.stop()
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)


async def handle_wake():
    print("[senses] wake detected")
    await manager.emit({ "type": "WAKE" })


async def handle_transcription(text: str):
    print(f"[senses] transcription: {text}")
    context = senses.get_context() if senses else {}

    await manager.emit({ "type": "TASK_START" })

    result = await handle_message(text, context)
    full_text = result["speech_text"]
    audio_url = result.get("audio_url") or await speak_tts(full_text)
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
async def recall_memory(query: str, _: None = Depends(require_api_key)):
    result = await memory_manager.recall(query)
    return { "result": result }

@app.get("/memory/week")
async def recall_week(_: None = Depends(require_api_key)):
    result = await memory_manager.recall_week()
    return { "result": result }

@app.post("/memory/fact")
async def store_fact(fact: str, _: None = Depends(require_api_key)):
    await memory_manager.remember_fact(fact)
    return { "ok": True }
