from typing import Dict, List, Any, Optional
import datetime

class MemoryStore:
    def __init__(self):
        # structure: { "session_id": { "history": [], "preferences": {}, "pending": None, "action_logs": [] } }
        self.store: Dict[str, Dict[str, Any]] = {}

    def _ensure_session(self, session_id: str):
        if session_id not in self.store:
            self.store[session_id] = {
                "history": [],
                "preferences": {},
                "pending": None,
                "action_logs": [],
                "permissions": {
                    "allow_high_risk": True,
                    "whatsapp_mode": "demo",
                },
            }

    def add_message(self, session_id: str, role: str, content: str):
        self._ensure_session(session_id)
        self.store[session_id]["history"].append({"role": role, "content": content})
        # Keep history manageable (last 20 turns)
        if len(self.store[session_id]["history"]) > 20:
            self.store[session_id]["history"] = self.store[session_id]["history"][-20:]

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        self._ensure_session(session_id)
        return self.store[session_id]["history"]

    def set_preference(self, session_id: str, key: str, value: str):
        self._ensure_session(session_id)
        self.store[session_id]["preferences"][key] = value

    def get_preferences(self, session_id: str) -> Dict[str, str]:
        self._ensure_session(session_id)
        return self.store[session_id]["preferences"]

    # ── Pending action for confirmation flow ──────────────────────────────────

    def set_pending_action(self, session_id: str, name: str, args: dict) -> None:
        """Store a pending tool call that is awaiting user confirmation."""
        self._ensure_session(session_id)
        self.store[session_id]["pending"] = {"name": name, "args": args}

    def get_pending_action(self, session_id: str) -> Optional[dict]:
        """Return pending action without clearing it."""
        self._ensure_session(session_id)
        return self.store[session_id].get("pending")

    def pop_pending_action(self, session_id: str) -> Optional[dict]:
        """Return and clear pending action."""
        self._ensure_session(session_id)
        pending = self.store[session_id].get("pending")
        self.store[session_id]["pending"] = None
        return pending

    def clear_pending_action(self, session_id: str) -> None:
        self._ensure_session(session_id)
        self.store[session_id]["pending"] = None

    # ── Action logging for audit trail ────────────────────────────────────────

    def log_action(self, session_id: str, action_name: str, params: Dict[str, Any], 
                   status: str, result: str, user_confirmed: bool = False,
                   undo_hint: Optional[str] = None):
        """Log an executed action for audit trail."""
        self._ensure_session(session_id)
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "action": action_name,
            "params": params,
            "status": status,
            "result": result[:200],  # Truncate long results
            "user_confirmed": user_confirmed,
            "undo_hint": undo_hint,
        }
        self.store[session_id]["action_logs"].append(log_entry)
        
        # Keep logs manageable (last 100 actions)
        if len(self.store[session_id]["action_logs"]) > 100:
            self.store[session_id]["action_logs"] = self.store[session_id]["action_logs"][-100:]

    def get_action_logs(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent action logs."""
        self._ensure_session(session_id)
        logs = self.store[session_id]["action_logs"]
        return logs[-limit:] if logs else []

    def get_last_action(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent action log."""
        self._ensure_session(session_id)
        logs = self.store[session_id]["action_logs"]
        return logs[-1] if logs else None

    # ── Permission preferences ────────────────────────────────────────────────

    def set_permission(self, session_id: str, key: str, value: Any):
        self._ensure_session(session_id)
        self.store[session_id]["permissions"][key] = value

    def get_permissions(self, session_id: str) -> Dict[str, Any]:
        self._ensure_session(session_id)
        return self.store[session_id]["permissions"]
