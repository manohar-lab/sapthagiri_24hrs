# Agentic Voice Assistant 🎙️🤖

A production-grade, real-time agentic voice assistant capable of multi-step reasoning, tool execution, and handling interruptions.

## 🌟 Core Features
- **Real-time Voice Interaction**: Streaming audio via WebSockets.
- **Agentic Execution**: Not just a chatbot. It plans, executes tools, and confirms actions.
- **Interrupt Handling**: Users can interrupt the agent mid-sentence to correct or change plans.
- **Human-like Fillers**: Provides immediate conversational fillers ("Just a second...", "Let me check that...") while executing long tasks.
- **Local STT & TTS**: Uses `faster-whisper` for fast, local transcription and `edge-tts` for high-quality voice.
- **Contextual Memory**: Remembers user preferences across the session.

## 🏗️ System Architecture

### Backend (FastAPI + WebSockets)
- **STT Engine**: `faster-whisper` processes audio chunks to text.
- **Agent Controller**: LangChain-based conversational agent with tool access.
- **Tools**: Mock implementations of real-world tasks (e.g., Booking Appointments, Sending Emails, Searching Info).
- **TTS Engine**: `edge-tts` generates streaming audio responses.
- **Session Memory**: In-memory store (extendable to Redis) retaining conversation history and extracted entities.

### Frontend (React + Vite)
- **Audio Streamer**: Captures mic input and streams via WebSockets.
- **Audio Player**: Plays incoming TTS streams, with the ability to halt playback on interruptions.
- **Modern UI**: Real-time visualizer, chat history, and agent state indicators (Listening, Thinking, Speaking, Executing).

## 🚀 Setup Instructions

### 1. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
Create a `.env` file in the `backend` directory:
```
OPENAI_API_KEY=your_openai_api_key  # Or use a local proxy like LM Studio/Ollama
```
Run the server:
```bash
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## 🎬 Demo Script for Judges

**Scenario 1: Multi-step Execution & Interruption**
1. **User**: "Book a doctor appointment for tomorrow at 5 PM."
2. **Agent**: "Okay, let me check the availability for tomorrow at 5 PM..." (Filler)
3. **User (Interrupts immediately)**: "Actually, make it 6 PM with Dr. Smith."
4. **Agent (Stops previous action)**: "Got it, changing that to 6 PM with Dr. Smith. Booking now..."
5. **Agent (After Tool Execution)**: "Your appointment with Dr. Smith is confirmed for tomorrow at 6 PM."

**Scenario 2: Memory & Hinglish**
1. **User**: "Mera naam Ravi hai, please remember this."
2. **Agent**: "Hello Ravi, I'll remember your name. How can I help you today?"
3. **User**: "Send an email to my boss saying I'll be late today."
4. **Agent**: "Drafting the email now... Okay Ravi, I've sent the email to your boss stating you will be late."

## 📁 Folder Structure
```
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI & WebSocket handler
│   │   ├── stt.py           # Whisper integration
│   │   ├── tts.py           # Edge-TTS integration
│   │   ├── agent.py         # LLM logic & Tool bindings
│   │   ├── tools.py         # Agentic actions
│   │   └── memory.py        # Session management
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── VoiceAssistant.jsx
│   │   │   ├── Visualizer.jsx
│   │   │   └── ChatLog.jsx
│   │   ├── styles/
│   │   └── main.jsx
│   └── index.html
└── README.md
```
