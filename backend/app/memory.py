from typing import Dict, List, Any

class MemoryStore:
    def __init__(self):
        # A simple in-memory store. 
        # structure: { "session_id": { "history": [], "preferences": {} } }
        self.store: Dict[str, Dict[str, Any]] = {}
        
    def _ensure_session(self, session_id: str):
        if session_id not in self.store:
            self.store[session_id] = {
                "history": [],
                "preferences": {}
            }
            
    def add_message(self, session_id: str, role: str, content: str):
        self._ensure_session(session_id)
        self.store[session_id]["history"].append({"role": role, "content": content})
        
        # Keep history manageable
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
