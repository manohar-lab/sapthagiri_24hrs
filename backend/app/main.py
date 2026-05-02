from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging

from app.stt import Transcriber
from app.tts import Synthesizer
from app.agent import AgentController
from app.memory import MemoryStore
from app.tools import undo_last_action

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Voice Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stt = Transcriber()
tts = Synthesizer()
memory = MemoryStore()
agent = AgentController(memory)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Voice Assistant Backend Running"}


@app.get("/api/logs/{session_id}")
def get_action_logs(session_id: str, limit: int = 50):
    """Retrieve action logs for a session."""
    logs = memory.get_action_logs(session_id, limit)
    return {"session_id": session_id, "logs": logs, "count": len(logs)}


@app.get("/api/preferences/{session_id}")
def get_preferences(session_id: str):
    """Retrieve user preferences for a session."""
    prefs = memory.get_preferences(session_id)
    return {"session_id": session_id, "preferences": prefs}


@app.get("/api/permissions/{session_id}")
def get_permissions(session_id: str):
    """Retrieve runtime permission settings."""
    return {"session_id": session_id, "permissions": memory.get_permissions(session_id)}


@app.post("/api/permissions/{session_id}")
def update_permissions(session_id: str, payload: dict):
    """Update runtime permission settings (e.g., whatsapp_mode/demo)."""
    for key, value in payload.items():
        memory.set_permission(session_id, key, value)
    return {"session_id": session_id, "permissions": memory.get_permissions(session_id)}


@app.post("/api/undo/{session_id}")
def undo_action(session_id: str, action_hint: str = "auto"):
    """Best-effort undo endpoint for external UI controls."""
    result = undo_last_action(action_hint)
    memory.log_action(session_id, "undo_last_action", {"action_hint": action_hint}, "success", result, True)
    return {"session_id": session_id, "result": result}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = "default_session" # In a real app, generate UUID per connection
    
    # Send an initial greeting
    greeting = "Hello! I am your AI assistant. How can I help you today?"
    audio_stream = await tts.synthesize(greeting)
    await websocket.send_bytes(audio_stream)
    await websocket.send_text(json.dumps({"type": "text", "text": greeting, "speaker": "agent"}))

    transcription_buffer = ""
    is_agent_speaking = False

    try:
        while True:
            try:
                data = await websocket.receive()

                if data.get("text"):
                    msg = json.loads(data["text"])
                    
                    # Handle Interruption Signal
                    if msg.get("type") == "interrupt":
                        logger.info("User interrupted!")
                        is_agent_speaking = False
                        await websocket.send_text(json.dumps({"type": "status", "status": "listening"}))
                        continue

                    # Handle Text Input (Fallback if STT is client-side or testing)
                    if msg.get("type") == "user_message":
                        user_text = msg.get("text", "")
                        if user_text.strip():
                            await process_user_turn(websocket, session_id, user_text)

                elif data.get("bytes"):
                    # Handle Audio Input (STT)
                    audio_chunk = data["bytes"]
                    text = await stt.transcribe(audio_chunk)
                    if text.strip():
                        await websocket.send_text(json.dumps({"type": "text", "text": text, "speaker": "user"}))
                        await process_user_turn(websocket, session_id, text)
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "status",
                            "status": "idle"
                        }))
            except WebSocketDisconnect:
                logger.info("Client disconnected gracefully")
                break
            except RuntimeError as e:
                if "disconnect" in str(e).lower() or "close" in str(e).lower():
                    logger.info("Client connection closed.")
                    break
                logger.exception(f"Runtime error in WS: {e}")
                break
            except Exception as e:
                logger.exception(f"Error while processing WS message: {e}")
                try:
                    await websocket.send_text(json.dumps({
                        "type": "text",
                        "text": "I hit an input-processing error. Please try again.",
                        "speaker": "agent"
                    }))
                    await websocket.send_text(json.dumps({"type": "status", "status": "idle"}))
                except:
                    break

    except WebSocketDisconnect:
        logger.info("Client disconnected")

async def process_user_turn(websocket: WebSocket, session_id: str, user_text: str):
    await websocket.send_text(json.dumps({"type": "status", "status": "thinking"}))
    
    # 1. Provide filler response for latency hiding
    filler = agent.get_filler(user_text)
    if filler:
        filler_audio = await tts.synthesize(filler)
        await websocket.send_bytes(filler_audio)
        await websocket.send_text(json.dumps({"type": "text", "text": filler, "speaker": "agent"}))

    # 2. Agent Execution (Tools, Reasoning)
    await websocket.send_text(json.dumps({"type": "status", "status": "executing"}))
    response_text = await agent.process_message(session_id, user_text)
    
    # 3. Final TTS Response
    await websocket.send_text(json.dumps({"type": "status", "status": "speaking"}))
    final_audio = await tts.synthesize(response_text)
    await websocket.send_bytes(final_audio)
    await websocket.send_text(json.dumps({"type": "text", "text": response_text, "speaker": "agent"}))
    
    await websocket.send_text(json.dumps({"type": "status", "status": "idle"}))

