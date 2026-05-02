import { useState, useEffect, useRef } from 'react';
import './index.css';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('idle'); // idle, listening, thinking, executing, speaking
  const [textInput, setTextInput] = useState('');
  
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioQueueRef = useRef([]);
  const currentAudioRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // WebSocket Connection
  useEffect(() => {
    connectWebSocket();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const connectWebSocket = () => {
    const ws = new WebSocket('ws://localhost:8000/ws');
    
    ws.onopen = () => {
      console.log('Connected to Agent Server');
      setStatus('idle');
    };

    ws.onmessage = async (event) => {
      if (typeof event.data === 'string') {
        const msg = JSON.parse(event.data);
        if (msg.type === 'status') {
          setStatus(msg.status);
        } else if (msg.type === 'text') {
          setMessages(prev => [...prev, { role: msg.speaker, text: msg.text }]);
        }
      } else if (event.data instanceof Blob) {
        // Handle incoming audio (TTS)
        const audioUrl = URL.createObjectURL(event.data);
        audioQueueRef.current.push(audioUrl);
        playNextAudio();
      }
    };

    ws.onclose = () => {
      console.log('Disconnected from Server');
      setTimeout(connectWebSocket, 3000); // Reconnect
    };

    wsRef.current = ws;
  };

  const playNextAudio = () => {
    if (currentAudioRef.current && !currentAudioRef.current.ended) return;
    if (audioQueueRef.current.length === 0) return;

    const audioUrl = audioQueueRef.current.shift();
    const audio = new Audio(audioUrl);
    currentAudioRef.current = audio;
    
    audio.play();
    setStatus('speaking');
    
    audio.onended = () => {
      setStatus('idle');
      playNextAudio();
    };
  };

  const stopAudio = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    audioQueueRef.current = [];
  };

  const startRecording = async () => {
    if (status === 'speaking') {
      handleInterrupt();
    }
    
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        // Send to backend via WebSocket
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(audioBlob);
        }
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setStatus('listening');
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('Could not access microphone.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setStatus('thinking');
    }
  };

  const handleOrbClick = () => {
    if (status === 'listening') {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const handleInterrupt = () => {
    stopAudio();
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
    }
    setStatus('idle');
  };

  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (!textInput.trim()) return;
    
    if (status === 'speaking') handleInterrupt();
    
    setMessages(prev => [...prev, { role: 'user', text: textInput }]);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'user_message', text: textInput }));
    }
    setTextInput('');
    setStatus('thinking');
  };

  return (
    <div className="app-container">
      <div className="header">
        <h1>Nova Agent</h1>
        <div className={`status-indicator status-${status}`}>
          <div className="dot"></div>
          {status === 'idle' ? 'Ready' : status.charAt(0).toUpperCase() + status.slice(1)}
        </div>
      </div>

      <div className="chat-area">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            {msg.text}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="controls">
        <button 
          className={`interrupt-btn ${status === 'speaking' ? 'visible' : ''}`}
          onClick={handleInterrupt}
        >
          Stop Speaking
        </button>

        <div className="orb-container">
          <button 
            className={`orb ${status === 'listening' ? 'listening' : ''} ${status === 'speaking' ? 'speaking' : ''}`}
            onClick={handleOrbClick}
          >
            {status === 'listening' ? (
              <svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
            ) : (
              <svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20c0 .55.45 1 1 1s1-.45 1-1v-2.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z"/></svg>
            )}
          </button>
        </div>

        <form className="input-fallback" onSubmit={handleTextSubmit}>
          <input 
            type="text" 
            placeholder="Type a message or use the mic..." 
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
          />
          <button type="submit">Send</button>
        </form>
      </div>
    </div>
  );
}
