# 🎯 Agentic Voice Assistant - System Controller

> A voice-controlled AI agent that executes real-world system-level and application-level tasks with built-in safety mechanisms.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🌟 Features

### 🎤 Voice-First Interaction
- Real-time voice input via WebSocket
- Natural text-to-speech responses
- Interrupt capability for dynamic conversations
- Text fallback for accessibility

### 🛠️ System Control Tools
- **📸 Screenshots**: Capture full screen or regions
- **🔊 Volume Control**: Increase, decrease, mute, or set specific levels
- **📋 Clipboard**: Get and set clipboard content
- **⌨️ Keyboard Automation**: Type text and press key combinations

### 🖥️ Application Management
- **Launch Apps**: Chrome, VS Code, Notepad, Calculator, Spotify, Discord, and more
- **Close Apps**: Safely terminate running applications (with confirmation)
- **Browser Control**: Open websites, perform Google searches
- **Multi-App Workflows**: Chain multiple app operations

### 💬 Communication & Automation
- **WhatsApp Messaging**: Send messages with safety confirmation
  - **Demo Mode**: Safe simulation for hackathons/testing
  - **Real Mode**: Actual sending via WhatsApp Web
- **Email**: Send emails (mock implementation, extensible)
- **Browser Automation**: Form filling, clicking (in development)

### 🔐 Safety Layer
- **3-Tier Risk System**:
  - **LOW**: Execute immediately (screenshots, volume)
  - **MEDIUM**: Execute with logging (app launch, typing)
  - **HIGH**: Require explicit confirmation (WhatsApp, close app)
- **Confirmation Flow**: Two-phase execution for sensitive actions
- **Action Logging**: Complete audit trail with timestamps
- **User Control**: Cancel or modify actions before execution

### 🧠 Memory & Context
- Conversation history management
- User preferences storage (name, contacts, etc.)
- Session-based memory
- Action logs accessible via API

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Node.js 16+
- OpenAI API key
- Windows 10/11 (primary support)

### Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd agentic-voice-assistant
```

2. **Backend Setup**
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows PowerShell
# or: source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

3. **Configure Environment**
```bash
# Create backend/.env
OPENAI_API_KEY=your_openai_api_key_here
```

4. **Start Backend**
```bash
uvicorn app.main:app --reload
```

5. **Frontend Setup** (new terminal)
```bash
cd frontend
npm install
npm run dev
```

6. **Open Browser**
```
http://localhost:5173
```

## 📖 Documentation

- **[Architecture](ARCHITECTURE.md)**: System design and data flow
- **[Setup Guide](SETUP_GUIDE.md)**: Detailed installation and configuration
- **[Demo Scenarios](DEMO_SCENARIOS.md)**: Example use cases and testing

## 🎬 Demo Scenarios

### Basic Commands

```
🗣️ "Take a screenshot"
✅ Executes immediately → Screenshot saved

🗣️ "Increase volume by 20%"
✅ Executes immediately → Volume increased

🗣️ "Open Chrome and search for AI news"
✅ Launches Chrome → Opens Google search

🗣️ "Type 'Hello World' and press Enter"
✅ Types into active window → Presses Enter
```

### Advanced Workflows

```
🗣️ "Send WhatsApp message to Ravi saying I'll be late"
🤖 "Do you want to send this WhatsApp message to Ravi: 'I'll be late'?"
🗣️ "Yes"
✅ Demo Mode: Simulated sending message

🗣️ "Open VS Code, take a screenshot, and copy the path"
✅ Multi-step execution → All actions completed
```

### Safety & Correction

```
🗣️ "Send a message to Ravi"
🤖 "Do you want to send this WhatsApp message to Ravi: '...'?"
🗣️ "No, send it to Aman instead"
🤖 "Do you want to send this WhatsApp message to Aman: '...'?"
🗣️ "Yes"
✅ Adapted to correction → Message sent
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                      │
│  Voice Input → WebSocket → Text Input → Confirmation UI │
└────────────────────────┬────────────────────────────────┘
                         │
                    WebSocket
                         │
┌────────────────────────┴────────────────────────────────┐
│                 BACKEND (FastAPI)                        │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  STT (Whisper) ←→ Agent Controller ←→ TTS       │  │
│  └──────────────────────┬───────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────▼───────────────────────────┐  │
│  │           SAFETY LAYER                            │  │
│  │  • Risk Assessment  • Confirmation  • Logging     │  │
│  └──────────────────────┬───────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────▼───────────────────────────┐  │
│  │         TOOL EXECUTION LAYER                      │  │
│  │  System Control │ App Management │ Automation     │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## 🛠️ Available Tools

| Category | Tools | Risk Level |
|----------|-------|------------|
| **System** | Screenshot, Volume Control, Clipboard | LOW |
| **Apps** | Launch App, Close App, Open Browser | MEDIUM |
| **Automation** | Type Text, Press Keys | MEDIUM |
| **Communication** | WhatsApp, Email | HIGH |
| **Memory** | Preferences, History | LOW |

## 🔧 Technology Stack

### Backend
- **FastAPI**: Async web framework
- **OpenAI GPT-4o-mini**: LLM with function calling
- **Faster-Whisper**: Speech-to-text
- **Edge-TTS**: Text-to-speech
- **PyAutoGUI**: GUI automation
- **pycaw**: Windows audio control
- **pywhatkit**: WhatsApp automation
- **Selenium**: Browser automation

### Frontend
- **React + Vite**: Modern UI framework
- **WebSocket API**: Real-time communication
- **Web Audio API**: Audio playback

## 📊 API Endpoints

```bash
# Health check
GET /

# Get action logs
GET /api/logs/{session_id}?limit=50

# Get user preferences
GET /api/preferences/{session_id}

# WebSocket connection
WS /ws
```

## 🔐 Safety Features

### Risk-Based Execution
- **Automatic**: Low-risk actions execute immediately
- **Logged**: Medium-risk actions are logged
- **Confirmed**: High-risk actions require explicit user approval

### Confirmation Flow
```python
1. Tool requests confirmation
2. Agent asks user
3. User approves/denies
4. Tool executes or cancels
5. Action logged with confirmation status
```

### Action Logging
```json
{
  "timestamp": "2026-05-02T14:30:00Z",
  "action": "send_whatsapp",
  "params": {"contact": "Ravi", "message": "I'll be late"},
  "status": "success",
  "user_confirmed": true
}
```

## 🎯 Use Cases

### Personal Assistant
- Take screenshots during meetings
- Control system volume hands-free
- Launch applications by voice
- Send quick messages

### Productivity Automation
- Multi-step workflows
- Keyboard shortcuts by voice
- Clipboard management
- Browser automation

### Accessibility
- Voice-controlled computer access
- Text-to-speech feedback
- Hands-free operation
- Text input fallback

### Development & Testing
- Automated testing workflows
- Screenshot documentation
- Quick app launching
- System control during demos

## 🚧 Roadmap

### Phase 1: Core Functionality ✅
- [x] Voice input/output
- [x] Basic system control
- [x] App management
- [x] Safety layer
- [x] Action logging

### Phase 2: Enhanced Automation 🚧
- [ ] Advanced browser automation
- [ ] File operations
- [ ] Email integration (SMTP)
- [ ] Calendar integration
- [ ] Scheduled tasks

### Phase 3: Intelligence 📋
- [ ] Context-aware suggestions
- [ ] Learning user preferences
- [ ] Predictive actions
- [ ] Multi-user profiles
- [ ] Voice biometric auth

### Phase 4: Expansion 📋
- [ ] Mobile app support
- [ ] Slack/Discord integration
- [ ] System monitoring
- [ ] Offline mode (local LLM)
- [ ] Plugin system

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Adding New Tools

1. Create function in `backend/app/tools.py`
2. Add to `AVAILABLE_TOOLS` dictionary
3. Add schema to `TOOLS_SCHEMA` list
4. Update risk level in `RISK_LEVELS`
5. Add demo scenario to `DEMO_SCENARIOS.md`
6. Test thoroughly

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- OpenAI for GPT-4o-mini API
- FastAPI for the excellent web framework
- Whisper for speech recognition
- Edge-TTS for natural voice synthesis
- The open-source community

## 📧 Contact

For questions, issues, or suggestions:
- Open an issue on GitHub
- Email: your-email@example.com
- Twitter: @yourhandle

---

**Built with ❤️ for hackathons and beyond!**

*Make your computer listen, understand, and act.*
