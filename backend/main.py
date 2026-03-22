import asyncio
import json
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, Dict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

connected: list[WebSocket] = []

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected.append(ws)
    print("frontend connected")
    try:
        while True:
            data = await ws.receive_text()
            print("from frontend:", data)
    except Exception:
        connected.remove(ws)
        print("frontend disconnected")

class EventBody(BaseModel):
    type: str
    class Config:
        extra = 'allow'

@app.post("/send")
async def send_event(event: EventBody):
    payload = event.model_dump()
    print("sending:", payload)
    for ws in connected:
        await ws.send_text(json.dumps(payload))
    return { "ok": True }

@app.post("/speak")
async def speak(text: str, audio_url: str = ""):
    event = { "type": "SPEECH", "text": text, "audio_url": audio_url }
    for ws in connected:
        await ws.send_text(json.dumps(event))
    return { "ok": True }