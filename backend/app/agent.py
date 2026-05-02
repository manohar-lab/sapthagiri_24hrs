import os
import json
import logging
from dotenv import load_dotenv
import openai

from app.memory import MemoryStore
from app.tools import (
    AVAILABLE_TOOLS,
    TOOLS_SCHEMA,
    update_preference,
    requires_confirmation,
    get_undo_hint,
)

load_dotenv()
logger = logging.getLogger(__name__)


class AgentController:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.groq.com/openai/v1"
        ) if self.api_key else None

        self.system_prompt = (
            "You are Nova, a fully autonomous AI execution agent with system-level control.\n"
            "Your purpose is NOT just to chat — you must understand user intent and execute real-world actions using available tools.\n\n"
            "--- 🔥 CORE CAPABILITIES ---\n"
            "You can perform: Screenshot capture, Open/close desktop applications, Control system volume, "
            "Type text and automate keyboard input, Send WhatsApp messages, Control mouse actions, "
            "Read screen content (if provided), Execute OS-level commands.\n\n"
            "--- ⚙️ AVAILABLE TOOLS ---\n"
            "You MUST use these functions when required: take_screenshot(), open_app(app_name), open_file(path), close_app(app_name), "
            "set_volume(level), type_text(text), send_whatsapp(number, message), move_mouse(x, y), click_mouse().\n\n"
            "--- 🧠 DECISION RULES ---\n"
            "1. Carefully analyze the user request.\n"
            "2. If the request requires an ACTION → CALL A TOOL.\n"
            "3. If the request is informational → respond normally.\n"
            "4. NEVER explain tools — JUST EXECUTE.\n"
            "5. NEVER say “I cannot” unless truly impossible.\n"
            "6. Always confirm before: Sending messages, Deleting or closing important apps.\n\n"
            "--- 🚀 EXECUTION RULES ---\n"
            "Be fast. Be precise. Minimize talking. Prioritize execution over explanation. "
            "Use the provided tools NATIVELY to take action. "
            "You are not a chatbot. You are a real-world AI operator (Jarvis-like system) that TAKES ACTION."
        )

    # ── Filler phrases ────────────────────────────────────────────────────────

    def get_filler(self, user_text: str) -> str:
        t = user_text.lower()
        if "book" in t or "appointment" in t:
            return "Let me check the schedule for that..."
        if "whatsapp" in t or ("message" in t and "email" not in t):
            return "Preparing the message..."
        if "email" in t:
            return "Drafting that now..."
        if "search" in t or "find" in t:
            return "Looking that up..."
        if "screenshot" in t:
            return "Taking a screenshot..."
        if "volume" in t:
            return "Adjusting volume..."
        if "open" in t or "launch" in t:
            return "Opening it now..."
        if "name" in t or "remember" in t:
            return "Got it."
        return ""

    # ── Main message handler ──────────────────────────────────────────────────

    async def process_message(self, session_id: str, user_text: str) -> str:
        self.memory.add_message(session_id, "user", user_text)

        # ---- Handle pending confirmation ----
        pending = self.memory.get_pending_action(session_id)
        if pending:
            text_lower = user_text.lower()
            if any(w in text_lower for w in ["yes", "yeah", "ok", "sure", "proceed", "send", "do it", "confirm"]):
                # Re-run the tool with confirmed=True
                self.memory.pop_pending_action(session_id)
                fn_name = pending["name"]
                raw_args = pending.get("args") or {}
                fn_args = {**raw_args, "confirmed": True}
                result = AVAILABLE_TOOLS[fn_name](**fn_args)
                self.memory.add_message(session_id, "assistant", result)
                return result
            if any(w in text_lower for w in ["no", "cancel", "stop", "don't", "do not"]):
                self.memory.clear_pending_action(session_id)
                reply = "Okay, I have cancelled that action."
                self.memory.add_message(session_id, "assistant", reply)
                return reply
            # If it's neither clear yes/no, treat as correction request and continue.

        # ---- No API key check ----
        if not self.client:
            return "API ERROR: Your Groq API key is missing. Please add a valid GROQ_API_KEY to your .env file."

        # ---- LLM path ----
        preferences = self.memory.get_preferences(session_id)
        pref_context = (
            "User Preferences:\n" + "\n".join(f"{k}: {v}" for k, v in preferences.items())
            if preferences else ""
        )
        messages = [{"role": "system", "content": self.system_prompt + "\n\n" + pref_context}]
        messages.extend(self.memory.get_history(session_id))

        try:
            response = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.7,
            )
            response_message = response.choices[0].message

            if response_message.tool_calls:
                messages.append(response_message)

                for tool_call in response_message.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        args_str = tool_call.function.arguments or "{}"
                        fn_args = json.loads(args_str)
                        if not isinstance(fn_args, dict):
                            fn_args = {}
                    except:
                        fn_args = {}
                    logger.info(f"[TOOL] {fn_name}({fn_args})")

                    if fn_name == "update_user_preference":
                        result = update_preference(
                            self.memory, session_id,
                            fn_args.get("key"), fn_args.get("value")
                        )
                        self.memory.log_action(session_id, fn_name, fn_args, "success", result)
                    elif fn_name in AVAILABLE_TOOLS:
                        permissions = self.memory.get_permissions(session_id)
                        if fn_name == "send_whatsapp" and "mode" not in fn_args:
                            fn_args["mode"] = permissions.get("whatsapp_mode", "real")
                        if requires_confirmation(fn_name, fn_args) and not fn_args.get("confirmed", False):
                            result = (
                                f"ACTION_NEEDS_CONFIRMATION: Do you want me to run '{fn_name}' "
                                f"with {fn_args}?"
                            )
                        elif fn_name == "browser_automation" and not permissions.get("allow_high_risk", True):
                            result = "Blocked by safety policy. High-risk browser automation is disabled."
                        else:
                            result = AVAILABLE_TOOLS[fn_name](**fn_args)

                        # Log the action
                        was_confirmed = fn_args.get("confirmed", False)
                        status = "success" if not result.startswith("Failed") else "failed"
                        self.memory.log_action(
                            session_id,
                            fn_name,
                            fn_args,
                            status,
                            result,
                            was_confirmed,
                            undo_hint=get_undo_hint(fn_name),
                        )
                    else:
                        result = f"Error: Tool '{fn_name}' not found."
                        self.memory.log_action(session_id, fn_name, fn_args, "error", result)

                    # ---- Safety: needs confirmation? ----
                    if isinstance(result, str) and result.startswith("ACTION_NEEDS_CONFIRMATION:"):
                        ask = result.replace("ACTION_NEEDS_CONFIRMATION:", "").strip()
                        self.memory.set_pending_action(session_id, fn_name, fn_args)
                        self.memory.add_message(session_id, "assistant", ask)
                        return ask

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": fn_name,
                        "content": result,
                    })

                # Second LLM call for final natural-language reply
                second = await self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.7,
                )
                final = second.choices[0].message.content
            else:
                final = response_message.content

            self.memory.add_message(session_id, "assistant", final)
            return final

        except Exception as e:
            logger.error(f"Agent error: {e}")
            if "429" in str(e) or "insufficient_quota" in str(e).lower() or getattr(e, "status_code", None) == 429:
                return "API ERROR: Your Groq API key is missing or invalid. Please check your GROQ_API_KEY in .env."
            return f"Sorry, I ran into an issue while processing your request: {e}"
