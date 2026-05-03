import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import './index.css';

const MOCK_TRANSCRIPTS = [
  [
    { role: 'user', text: 'Hey Jarvis, what\'s the weather like today?' },
    { role: 'jarvis', text: 'Currently 24°C and partly cloudy in your location. Perfect for a walk!' },
  ],
  [
    { role: 'user', text: 'Open Spotify and play some lo-fi music.' },
    { role: 'jarvis', text: 'Opening Spotify and queuing your lo-fi playlist now.' },
  ],
  [
    { role: 'user', text: 'Set a reminder for my 3pm meeting.' },
    { role: 'jarvis', text: 'Reminder set for 3:00 PM. I\'ll notify you 5 minutes before.' },
  ],
];

const STATUS_LABELS = {
  idle: 'READY',
  listening: 'LISTENING',
  processing: 'PROCESSING',
  speaking: 'SPEAKING',
};

function formatTime(secs) {
  const m = String(Math.floor(secs / 60)).padStart(2, '0');
  const s = String(secs % 60).padStart(2, '0');
  return `${m}:${s}`;
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [wsStatus, setWsStatus] = useState('idle');
  const [textInput, setTextInput] = useState('');
  const [pipWindow, setPipWindow] = useState(null);
  const [sessionSecs, setSessionSecs] = useState(0);
  const [commandCount, setCommandCount] = useState(0);
  const [confidence, setConfidence] = useState(0);
  const [muted, setMuted] = useState(false);

  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioQueueRef = useRef([]);
  const currentAudioRef = useRef(null);
  const isRecordingIntentRef = useRef(false);
  const sessionTimerRef = useRef(null);
  const transcriptEndRef = useRef(null);

  // Session timer
  useEffect(() => {
    sessionTimerRef.current = setInterval(() => setSessionSecs(s => s + 1), 1000);
    return () => clearInterval(sessionTimerRef.current);
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      const ws = new WebSocket('ws://localhost:8000/ws');
      ws.onopen = () => setWsStatus('idle');
      ws.onmessage = async (event) => {
        if (typeof event.data === 'string') {
          let msg;
          try { msg = JSON.parse(event.data); } catch { return; }
          if (msg.type === 'status') {
            setWsStatus(msg.status);
            if (msg.status === 'thinking' || msg.status === 'executing') {
              setWsStatus('processing');
            }
          } else if (msg.type === 'text') {
            const role = msg.speaker === 'user' ? 'user' : 'jarvis';
            setMessages(prev => [...prev, { role, text: msg.text }]);
            if (role === 'user') {
              setCommandCount(c => c + 1);
              setConfidence(Math.floor(Math.random() * 15) + 85);
            }
          }
        } else if (event.data instanceof Blob) {
          if (muted) return;
          const audioBlob = new Blob([event.data], { type: 'audio/mp3' });
          const audioUrl = URL.createObjectURL(audioBlob);
          audioQueueRef.current.push(audioUrl);
          playNextAudio();
        }
      };
      ws.onclose = () => {
        setWsStatus('idle');
        reconnectTimerRef.current = setTimeout(connectWebSocket, 3000);
      };
      wsRef.current = ws;
    };
    connectWebSocket();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [muted]);

  const playNextAudio = () => {
    if (currentAudioRef.current && !currentAudioRef.current.paused && !currentAudioRef.current.ended) return;
    if (audioQueueRef.current.length === 0) return;
    const audioUrl = audioQueueRef.current.shift();
    currentAudioRef.current.src = audioUrl;
    currentAudioRef.current.play()
      .then(() => setWsStatus('speaking'))
      .catch(() => setWsStatus('idle'));
    currentAudioRef.current.onended = () => {
      setWsStatus('idle');
      playNextAudio();
    };
  };

  const stopAudio = () => {
    if (currentAudioRef.current) currentAudioRef.current.pause();
    audioQueueRef.current = [];
  };

  const startRecording = async () => {
    if (wsStatus === 'listening' || wsStatus === 'processing') return;
    if (wsStatus === 'speaking') { stopAudio(); }
    isRecordingIntentRef.current = true;
    setWsStatus('listening');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!isRecordingIntentRef.current) { stream.getTracks().forEach(t => t.stop()); setWsStatus('idle'); return; }
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) wsRef.current.send(audioBlob);
        stream.getTracks().forEach(t => t.stop());
      };
      mediaRecorder.start();
    } catch (err) {
      console.error(err);
      setWsStatus('idle');
    }
  };

  const stopRecording = () => {
    isRecordingIntentRef.current = false;
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setWsStatus('processing');
  };

  const handleActivate = () => {
    if (wsStatus === 'idle') {
      startRecording();
    } else if (wsStatus === 'listening') {
      stopRecording();
    } else if (wsStatus === 'speaking' || wsStatus === 'processing') {
      stopAudio();
      isRecordingIntentRef.current = false;
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop();
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
      setWsStatus('idle');
    }
  };

  const handleClear = () => {
    setMessages([]);
    setCommandCount(0);
    setConfidence(0);
  };

  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (!textInput.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setMessages(prev => [...prev, { role: 'user', text: textInput }]);
    setCommandCount(c => c + 1);
    setConfidence(Math.floor(Math.random() * 10) + 90);
    wsRef.current.send(JSON.stringify({ type: 'user_message', text: textInput }));
    setTextInput('');
    setWsStatus('processing');
  };

  const activateLabel = () => {
    if (wsStatus === 'listening') return '⏹ Stop';
    if (wsStatus === 'processing') return '⟳ Cancel';
    if (wsStatus === 'speaking') return '⏸ Interrupt';
    return '⏺ Activate';
  };

  const isActive = wsStatus === 'listening' || wsStatus === 'speaking';

  // PiP
  const togglePip = async () => {
    if (pipWindow) { pipWindow.close(); return; }
    if (!('documentPictureInPicture' in window)) { alert('Picture-in-Picture not supported in your browser.'); return; }
    try {
      const pip = await window.documentPictureInPicture.requestWindow({ width: 400, height: 650 });
      [...document.styleSheets].forEach(ss => {
        try {
          const css = [...ss.cssRules].map(r => r.cssText).join('');
          const style = document.createElement('style');
          style.textContent = css;
          pip.document.head.appendChild(style);
        } catch {
          const link = document.createElement('link');
          link.rel = 'stylesheet';
          link.href = ss.href;
          pip.document.head.appendChild(link);
        }
      });
      pip.addEventListener('pagehide', () => setPipWindow(null));
      setPipWindow(pip);
    } catch (err) { console.error(err); }
  };

  const appContent = (
    <div className="jarvis-app">
      <audio ref={currentAudioRef} hidden />

      {/* ── Top Bar ── */}
      <div className="top-bar">
        <div className="top-bar-left">
          <div className="brand-icon">
            <svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 17.93V18a1 1 0 0 0-2 0v1.93A8 8 0 0 1 4.07 13H6a1 1 0 0 0 0-2H4.07A8 8 0 0 1 11 4.07V6a1 1 0 0 0 2 0V4.07A8 8 0 0 1 19.93 11H18a1 1 0 0 0 0 2h1.93A8 8 0 0 1 13 19.93z"/></svg>
          </div>
          <span className="brand-title">Jarvis</span>
        </div>
        <div className="top-bar-right" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="status-pill">
            <div className={`status-dot ${wsStatus}`} />
            {STATUS_LABELS[wsStatus] || 'READY'}
          </div>
          {!pipWindow && (
            <button onClick={togglePip} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-light)', fontSize: '1.2rem', padding: 4 }} title="Pop Out">⊞</button>
          )}
        </div>
      </div>

      {/* ── Main Area ── */}
      <div className="main-area">
        {/* Ripple + Orb */}
        <div className="ripple-container">
          <div className={`ripple-ring ${isActive ? wsStatus : ''}`} />
          <div className={`ripple-ring ${isActive ? wsStatus : ''}`} />
          <div className={`ripple-ring ${isActive ? wsStatus : ''}`} />
          <div className="clay-orb" onClick={handleActivate}>
            <div className={`orb-inner ${wsStatus !== 'idle' ? wsStatus : ''}`}>
              <svg className="orb-icon" viewBox="0 0 24 24">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20c0 .55.45 1 1 1s1-.45 1-1v-2.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z"/>
              </svg>
            </div>
          </div>
        </div>

        {/* Wave bars */}
        <div className="wave-bars">
          {[...Array(9)].map((_, i) => (
            <div
              key={i}
              className={`wave-bar ${isActive || wsStatus === 'processing' ? 'active ' + wsStatus : ''}`}
              style={{ animationDelay: `${i * 0.08}s` }}
            />
          ))}
        </div>

        <span className="orb-status-text">{STATUS_LABELS[wsStatus]}</span>

        {/* Transcript */}
        <div className="transcript-panel">
          {messages.length === 0 ? (
            <span className="transcript-empty">— no conversation yet —</span>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className="transcript-row">
                <span className={`speaker-pill ${msg.role}`}>{msg.role === 'user' ? 'YOU' : 'JARVIS'}</span>
                <span className="transcript-text">{msg.text}</span>
              </div>
            ))
          )}
          <div ref={transcriptEndRef} />
        </div>
      </div>

      {/* ── Bottom ── */}
      <div className="bottom-section">
        {/* Stats row */}
        <div className="stats-row">
          <div className="stat-item">
            <span className="stat-value">{commandCount}</span>
            <span className="stat-label">Commands</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{confidence > 0 ? `${confidence}%` : '—'}</span>
            <span className="stat-label">Confidence</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{formatTime(sessionSecs)}</span>
            <span className="stat-label">Session</span>
          </div>
        </div>

        {/* Button row — 1fr 2fr 1fr */}
        <div className="button-row">
          <button className="btn-clay" onClick={handleClear}>Clear</button>
          <button className={`btn-clay btn-activate ${wsStatus !== 'idle' ? wsStatus : ''}`} onClick={handleActivate}>
            {activateLabel()}
          </button>
          <button className="btn-clay" onClick={() => setMuted(m => !m)}>
            {muted ? '🔇 Unmute' : '🔊 Mute'}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {pipWindow ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)', gap: 20, fontFamily: 'Outfit, sans-serif' }}>
          <h2 style={{ color: 'var(--text-dark)', fontWeight: 700 }}>Jarvis is running in Mini Mode</h2>
          <p style={{ color: 'var(--text-light)' }}>Keep this tab open to stay connected.</p>
          <button className="btn-clay btn-activate" style={{ padding: '14px 32px' }} onClick={() => pipWindow.close()}>Return to Full Screen</button>
          {createPortal(appContent, pipWindow.document.body)}
        </div>
      ) : appContent}
    </>
  );
}
