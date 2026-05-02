from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging

from app.stt import Transcriber
from app.tts import Synthesizer
from app.agent import AgentController
from app.memory import MemoryStore

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
            data = await websocket.receive()

            if "text" in data:
                msg = json.loads(data["text"])
                
                # Handle Interruption Signal
                if msg.get("type") == "interrupt":
                    logger.info("User interrupted!")
                    # Cancel any ongoing TTS/Agent processes here if they were running in background tasks
                    is_agent_speaking = False
                    await websocket.send_text(json.dumps({"type": "status", "status": "listening"}))
                    continue

                # Handle Text Input (Fallback if STT is client-side or testing)
                if msg.get("type") == "user_message":
                    user_text = msg.get("text", "")
                    await process_user_turn(websocket, session_id, user_text)

            elif "bytes" in data:
                # Handle Audio Input (STT)
                audio_chunk = data["bytes"]
                # In a real streaming scenario, we'd append to a buffer and process VAD (Voice Activity Detection)
                # For simplicity here, we assume the frontend sends a complete utterance chunk.
                # A more advanced implementation uses WebRTC or chunked STT.
                
                text = await stt.transcribe(audio_chunk)
                if text.strip():
                    await websocket.send_text(json.dumps({"type": "text", "text": text, "speaker": "user"}))
                    await process_user_turn(websocket, session_id, text)

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

