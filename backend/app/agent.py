import os
import re
import json
import logging
import inspect
import datetime
from dotenv import load_dotenv
import openai

from app.memory import MemoryStore
from app.tools import (
    AVAILABLE_TOOLS,
    TOOLS_SCHEMA,
    update_preference,
    requires_confirmation,
    get_undo_hint,
    search_on_site,
    open_browser,
    SITE_SEARCH_URLS,
    SITE_HOME_URLS,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local intent router — handles the most common commands instantly,
# without involving the LLM. This avoids Groq tool_use_failed errors for
# simple requests like "open amazon" or "search for laptop on flipkart".
# ---------------------------------------------------------------------------

# Build a flat set of known site names for fast lookup
_KNOWN_SITES = set(SITE_SEARCH_URLS.keys()) | set(SITE_HOME_URLS.keys())

# Voice/ASR typo normalization — maps common speech-recognition mistakes to real site names
_VOICE_SITE_ALIASES = {
    # amazon variations
    "amazon dottin": "amazon", "amazon dot in": "amazon", "amazon.in": "amazon",
    "amazon india": "amazon", "amazone": "amazon", "amazoon": "amazon",
    # flipkart
    "flip kart": "flipkart", "flip cart": "flipkart", "flipcart": "flipkart",
    # youtube
    "you tube": "youtube", "utube": "youtube", "u tube": "youtube",
    # netflix
    "net flex": "netflix", "net flix": "netflix", "netflex": "netflix",
    "netfli": "netflix", "netflix dot com": "netflix",
    # google
    "goo gle": "google",
    # whatsapp
    "whats app": "whatsapp", "watsapp": "whatsapp",
    # instagram
    "insta": "instagram", "insta gram": "instagram",
    # others
    "you tube music": "youtube", "yt": "youtube",
    "fb": "facebook", "face book": "facebook",
    "linked in": "linkedin",
    "stack overflow": "stackoverflow",
    "git hub": "github",
    "red dit": "reddit",
    "big basket": "bigbasket",
    "blink it": "blinkit",
}

# Add all SITE_HOME_URLS sites so they're also in SITE_SEARCH_URLS
# (allows searching on sites that only have home URLs)
_ALL_KNOWN_SITES = _KNOWN_SITES | set(_VOICE_SITE_ALIASES.values())


def _normalize_site(raw: str) -> str:
    """Normalize a site name: apply aliases, strip noise words."""
    s = raw.strip().lower()
    # Check aliases first (longest match first)
    for alias in sorted(_VOICE_SITE_ALIASES, key=len, reverse=True):
        if alias in s:
            s = s.replace(alias, _VOICE_SITE_ALIASES[alias]).strip()
            break
    # Strip trailing noise words
    for noise in [" website", " site", " app", " page", " dottin",
                  " dot in", " dot com", ".in", ".com"]:
        if s.endswith(noise):
            s = s[: -len(noise)].strip()
    return s


def _match_site(candidate: str) -> str | None:
    """
    Match a candidate string to a known site key.
    Uses EXACT word-level matching to avoid false matches
    (e.g., 'x' substring inside 'netflix').
    Returns the matched site key or None.
    """
    candidate = _normalize_site(candidate)
    # 1. Exact match
    if candidate in _ALL_KNOWN_SITES:
        return candidate
    # 2. Longest site key whose ALL words appear as whole words in the candidate
    for site_key in sorted(_ALL_KNOWN_SITES, key=len, reverse=True):
        # Use word-boundary check: every word in site_key must be a word in candidate
        words = site_key.split()
        if all(re.search(r'\b' + re.escape(w) + r'\b', candidate) for w in words):
            return site_key
    # 3. Candidate is a prefix/suffix of a known site (only if candidate >= 4 chars)
    if len(candidate) >= 4:
        for site_key in sorted(_ALL_KNOWN_SITES, key=len, reverse=True):
            if site_key.startswith(candidate) or candidate.startswith(site_key):
                return site_key
    return None


# --- Regex patterns ---

# "search for X on SITE" / "find X on SITE" / "show me X on SITE"
_SEARCH_ON_SITE_RE = re.compile(
    r'(?:search(?:\s+for)?|find|look\s+for|show\s+me|get)\s+(.+?)\s+on\s+([a-z0-9. ]+?)(?:\s*$|\s+and\b)',
    re.IGNORECASE,
)
# "search SITE for X"
_SEARCH_SITE_FOR_RE = re.compile(
    r'(?:search|find)\s+([a-z0-9. ]+?)\s+for\s+(.+)',
    re.IGNORECASE,
)
# "go to SITE and search for X" / "open SITE and search for X" / "open SITE and find X"
_GOTO_AND_SEARCH_RE = re.compile(
    r'(?:go\s+to|open|navigate\s+to)\s+([a-z0-9. ]+?)\s+and\s+(?:search(?:\s+for)?|find|look\s+for)\s+(.+)',
    re.IGNORECASE,
)
# "open SITE" / "go to SITE" / "launch SITE" / "show SITE"
_OPEN_SITE_RE = re.compile(
    r'(?:open|go\s+to|launch|navigate\s+to|show|start|visit)\s+([a-z0-9. ]+)',
    re.IGNORECASE,
)


def _local_route(user_text: str):
    """
    Try to handle the request locally without LLM.
    Returns (tool_name, result_str) or (None, None) if not handled.
    Priority order:
      1. "X on SITE" → search_on_site
      2. "SITE for X" → search_on_site
      3. "go to SITE and search X" → search_on_site
      4. "open SITE" → open_browser
    """
    t = user_text.strip()

    # --- 1. pattern: search X on SITE ---
    m = _SEARCH_ON_SITE_RE.search(t)
    if m:
        query = m.group(1).strip()
        site_raw = m.group(2).strip().rstrip('.')
        site = _match_site(site_raw) or site_raw
        result = search_on_site(site, query)
        return "search_on_site", result

    # --- 2. pattern: search SITE for X ---
    m = _SEARCH_SITE_FOR_RE.search(t)
    if m:
        site_raw = m.group(1).strip()
        query    = m.group(2).strip()
        site = _match_site(site_raw)
        if site:
            result = search_on_site(site, query)
            return "search_on_site", result

    # --- 3. pattern: go to SITE and search X / open SITE and search X ---
    m = _GOTO_AND_SEARCH_RE.search(t)
    if m:
        site_raw = m.group(1).strip()
        query    = m.group(2).strip()
        site = _match_site(site_raw) or site_raw
        result = search_on_site(site, query)
        return "search_on_site", result

    # --- 4. pattern: open / go to SITE ---
    m = _OPEN_SITE_RE.search(t)
    if m:
        candidate = m.group(1).strip().rstrip('.')
        site = _match_site(candidate)
        if site:
            result = open_browser(site)
            return "open_browser", result

    return None, None


def _parse_malformed_tool_call(text: str):
    """
    Groq sometimes returns malformed XML-style tool calls like:
        <function=tool_name({"arg": "val"})</function>
    or:
        <function=tool_name>{"arg": "val"}</function>
    This parser extracts the tool name + args dict from those strings.
    Returns (fn_name, fn_args_dict) or (None, None).
    """
    if not text:
        return None, None

    # Pattern 1: <function=NAME(JSON)</function>
    m = re.search(r'<function=([a-z_]+)\((\{.*?\})\)</function>', text, re.DOTALL)
    if m:
        fn_name = m.group(1)
        try:
            fn_args = json.loads(m.group(2))
            return fn_name, fn_args
        except Exception:
            pass

    # Pattern 2: <function=NAME>JSON</function>
    m = re.search(r'<function=([a-z_]+)>(.*?)</function>', text, re.DOTALL)
    if m:
        fn_name = m.group(1)
        try:
            fn_args = json.loads(m.group(2).strip())
            return fn_name, fn_args
        except Exception:
            pass

    # Pattern 3: bare function call anywhere in text
    m = re.search(r'\b([a-z_]+)\((\{.*?\})\)', text, re.DOTALL)
    if m:
        fn_name = m.group(1)
        if fn_name in AVAILABLE_TOOLS:
            try:
                fn_args = json.loads(m.group(2))
                return fn_name, fn_args
            except Exception:
                pass

    return None, None


def _execute_tool(fn_name: str, fn_args: dict, session_id: str, memory: MemoryStore,
                  permissions: dict) -> str:
    """Execute a single tool and return the result string."""
    if fn_name == "update_user_preference":
        result = update_preference(
            memory, session_id,
            fn_args.get("key"), fn_args.get("value")
        )
        memory.log_action(session_id, fn_name, fn_args, "success", result)
        return result

    if fn_name not in AVAILABLE_TOOLS:
        result = f"Error: Tool '{fn_name}' not found."
        memory.log_action(session_id, fn_name, fn_args, "error", result)
        return result

    if fn_name == "send_whatsapp" and "mode" not in fn_args:
        fn_args["mode"] = permissions.get("whatsapp_mode", "real")

    if requires_confirmation(fn_name, fn_args) and not fn_args.get("confirmed", False):
        return (
            f"ACTION_NEEDS_CONFIRMATION: Do you want me to run '{fn_name}' "
            f"with {fn_args}?"
        )

    if fn_name == "browser_automation" and not permissions.get("allow_high_risk", True):
        return "Blocked by safety policy. High-risk browser automation is disabled."

    fn = AVAILABLE_TOOLS[fn_name]
    sig = inspect.signature(fn)
    filtered_args = {k: v for k, v in fn_args.items() if k in sig.parameters}

    try:
        result = fn(**filtered_args)
    except Exception as e:
        logger.error(f"Error executing tool {fn_name}: {e}")
        result = f"Error: Failed to execute {fn_name}. {e}"

    was_confirmed = fn_args.get("confirmed", False)
    status = "success" if not str(result).startswith("Failed") else "failed"
    memory.log_action(
        session_id, fn_name, fn_args, status, result, was_confirmed,
        undo_hint=get_undo_hint(fn_name),
    )
    return result


class AgentController:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.groq.com/openai/v1"
        ) if self.api_key else None

        self.system_prompt = (
            "You are Nova, a fully autonomous AI assistant and system controller.\n"
            "Execute real-world actions using tools. Be concise and action-first.\n\n"
            "TOOL SELECTION GUIDE:\n"
            "- 'search X on Flipkart/Amazon/YouTube' => search_on_site(site, query)\n"
            "- 'open Flipkart/Amazon/YouTube' => open_browser(query)\n"
            "- 'open Notepad/Chrome/VSCode' => open_app(app_name)\n"
            "- 'take screenshot' => take_screenshot()\n"
            "- 'volume up/down' => control_volume(action)\n"
            "- 'type ...' => type_text(text)\n"
            "- 'press Ctrl+C' => press_keys(keys)\n"
            "- 'send WhatsApp to ...' => send_whatsapp(contact, message)\n\n"
            "RULES:\n"
            "1. Always call a tool for action requests. Never just describe what you would do.\n"
            "2. For web searches on specific sites, use search_on_site.\n"
            "3. Keep responses short. One sentence confirmation after tool execution.\n"
            "4. If unsure which tool to use, pick the most relevant one and execute.\n"
            "5. NEVER output raw function call syntax. Use proper tool_calls only.\n"
            "6. For general knowledge questions (like the time), conversational chitchat, or asking for facts, DO NOT use any tools. Answer directly in natural language."
        )

        # Structured intent-parsing prompt (returns strict JSON only)
        self.intent_prompt = (
            "You are an AI system controller that converts user commands into structured JSON actions for execution.\n\n"
            "Your job is to:\n"
            "1. Understand the user's intent\n"
            "2. Extract key entities (app name, file name, path, message, etc.)\n"
            "3. Return a STRICT JSON response (no explanation, no extra text)\n\n"
            "SUPPORTED ACTION TYPES:\n"
            "1. open_app\n2. open_website\n3. find_file\n4. open_file\n"
            "5. system_control (volume, brightness, etc.)\n"
            "6. send_message\n7. search_web\n8. unknown\n\n"
            "JSON FORMAT:\n"
            "{\"action\": \"<action_type>\", \"parameters\": {\"app_name\": \"\", \"url\": \"\", "
            "\"file_name\": \"\", \"search_path\": \"\", \"message\": \"\", \"recipient\": \"\", "
            "\"value\": \"\", \"query\": \"\"}}\n\n"
            "RULES:\n"
            "- Always return valid JSON only\n"
            "- Do not include explanations\n"
            "- If information is missing, leave fields as empty string \"\"\n"
            "- If unsure, set action = \"unknown\"\n"
            "- Normalize paths (e.g., 'C drive' → 'C:\\\\')\n"
            "- Extract closest possible meaning from user input\n"
            "- Prefer file search over navigation (never simulate clicks)\n"
            "- If user says 'open YouTube', treat as open_website with URL\n"
            "- If user says 'find' or 'get', use find_file\n"
            "- If user says 'open file', use open_file\n"
        )

    # -- Filler phrases -------------------------------------------------------

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

    # -- Intent parser (JSON structured output) --------------------------------

    async def _parse_intent(self, user_text: str) -> dict | None:
        """
        Uses a dedicated LLM call to parse the user command into a strict JSON
        action object. Returns the parsed dict, or None if it fails / is 'unknown'.
        """
        if not self.client:
            return None
        try:
            resp = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": self.intent_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.0,
                max_tokens=256,
            )
            raw = (resp.choices[0].message.content or "").strip()
            # Strip markdown code fences if present
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw).strip()
            parsed = json.loads(raw)
            if parsed.get("action") and parsed["action"] != "unknown":
                return parsed
        except Exception as e:
            logger.debug(f"[INTENT_PARSE] Failed: {e}")
        return None

    def _dispatch_intent(self, intent: dict, session_id: str, permissions: dict) -> str | None:
        """
        Maps a parsed JSON intent to a concrete tool call.
        Returns a result string if handled, else None.
        """
        action = intent.get("action", "unknown")
        params = intent.get("parameters", {})

        if action == "open_app":
            app = params.get("app_name", "")
            if app and "open_app" in AVAILABLE_TOOLS:
                return _execute_tool("open_app", {"app_name": app}, session_id, self.memory, permissions)

        elif action == "open_website":
            url = params.get("url", "") or params.get("app_name", "")
            if url and "open_browser" in AVAILABLE_TOOLS:
                return _execute_tool("open_browser", {"query": url}, session_id, self.memory, permissions)

        elif action == "search_web":
            query = params.get("query", "")
            site = params.get("app_name", "")  # e.g. "youtube"
            if query and site and "search_on_site" in AVAILABLE_TOOLS:
                return _execute_tool("search_on_site", {"site": site, "query": query}, session_id, self.memory, permissions)
            elif query and "search_on_site" in AVAILABLE_TOOLS:
                return _execute_tool("search_on_site", {"site": "google", "query": query}, session_id, self.memory, permissions)

        elif action == "find_file":
            fname = params.get("file_name", "")
            path = params.get("search_path", "C:\\")
            if fname and "find_file" in AVAILABLE_TOOLS:
                return _execute_tool("find_file", {"file_name": fname, "search_path": path}, session_id, self.memory, permissions)

        elif action == "open_file":
            fname = params.get("file_name", "")
            if fname and "open_file" in AVAILABLE_TOOLS:
                return _execute_tool("open_file", {"path": fname}, session_id, self.memory, permissions)

        elif action == "send_message":
            recipient = params.get("recipient", "")
            message = params.get("message", "")
            if recipient and message and "send_whatsapp" in AVAILABLE_TOOLS:
                return _execute_tool("send_whatsapp", {"contact": recipient, "message": message}, session_id, self.memory, permissions)

        elif action == "system_control":
            query = params.get("query", "").lower()
            value = params.get("value", "")
            if "volume" in query and "control_volume" in AVAILABLE_TOOLS:
                direction = "up" if any(w in query for w in ["increase", "up", "raise"]) else "down"
                return _execute_tool("control_volume", {"action": direction, "value": value}, session_id, self.memory, permissions)

        return None

    # -- Main message handler -------------------------------------------------

    async def process_message(self, session_id: str, user_text: str) -> str:
        self.memory.add_message(session_id, "user", user_text)

        # ---- Handle pending confirmation ----
        pending = self.memory.get_pending_action(session_id)
        if pending:
            text_lower = user_text.lower()
            if any(w in text_lower for w in ["yes", "yeah", "ok", "sure", "proceed", "send", "do it", "confirm"]):
                self.memory.pop_pending_action(session_id)
                fn_name = pending["name"]
                raw_args = pending.get("args") or {}
                fn_args = {**raw_args, "confirmed": True}
                permissions = self.memory.get_permissions(session_id)
                result = _execute_tool(fn_name, fn_args, session_id, self.memory, permissions)
                self.memory.add_message(session_id, "assistant", result)
                return result
            if any(w in text_lower for w in ["no", "cancel", "stop", "don't", "do not"]):
                self.memory.clear_pending_action(session_id)
                reply = "Okay, I have cancelled that action."
                self.memory.add_message(session_id, "assistant", reply)
                return reply

        # ---- Try local intent routing first (no LLM call needed) ----
        tool_name, local_result = _local_route(user_text)
        if local_result is not None:
            logger.info(f"[LOCAL_ROUTE] {tool_name} -> {local_result[:80]}")
            if isinstance(local_result, str) and local_result.startswith("ACTION_NEEDS_CONFIRMATION:"):
                ask = local_result.replace("ACTION_NEEDS_CONFIRMATION:", "").strip()
                self.memory.set_pending_action(session_id, tool_name, {})
                self.memory.add_message(session_id, "assistant", ask)
                return ask
            self.memory.add_message(session_id, "assistant", local_result)
            return local_result

        # ---- No API key check ----
        if not self.client:
            return "API ERROR: Your Groq API key is missing. Please add a valid GROQ_API_KEY to your .env file."

        # ---- Structured JSON intent parsing (mid-tier router) ----
        permissions = self.memory.get_permissions(session_id)
        intent = await self._parse_intent(user_text)
        if intent:
            logger.info(f"[INTENT_ROUTER] Parsed intent: {intent}")
            intent_result = self._dispatch_intent(intent, session_id, permissions)
            if intent_result is not None:
                if isinstance(intent_result, str) and intent_result.startswith("ACTION_NEEDS_CONFIRMATION:"):
                    ask = intent_result.replace("ACTION_NEEDS_CONFIRMATION:", "").strip()
                    self.memory.set_pending_action(session_id, intent.get("action", ""), {})
                    self.memory.add_message(session_id, "assistant", ask)
                    return ask
                self.memory.add_message(session_id, "assistant", intent_result)
                return intent_result

        # ---- Full LLM + tool-calling path ----
        preferences = self.memory.get_preferences(session_id)
        pref_context = (
            "User Preferences:\n" + "\n".join(f"{k}: {v}" for k, v in preferences.items())
            if preferences else ""
        )
        now_str = datetime.datetime.now().strftime("%I:%M %p, %A, %B %d, %Y")
        sys_content = self.system_prompt + f"\n\nCurrent System Time: {now_str}"
        if pref_context:
            sys_content += "\n\n" + pref_context

        messages = [{"role": "system", "content": sys_content}]
        messages.extend(self.memory.get_history(session_id))

        final = await self._call_llm_with_tools(messages, session_id)
        self.memory.add_message(session_id, "assistant", final)
        return final

    async def _call_llm_with_tools(self, messages: list, session_id: str) -> str:
        """
        Calls the LLM with tool support.
        On Groq 400 tool_use_failed errors, parses the malformed output and
        executes the tool locally, OR retries as a plain text call.
        """
        permissions = self.memory.get_permissions(session_id)

        try:
            response = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.3,          # Lower temp = more reliable tool calls
                parallel_tool_calls=False, # One tool at a time to avoid confusion
            )
            response_message = response.choices[0].message

            if not response_message.tool_calls:
                return response_message.content or "Done."

            # --- Process tool calls ---
            messages.append(response_message)
            for tool_call in response_message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments or "{}")
                    if not isinstance(fn_args, dict):
                        fn_args = {}
                except Exception:
                    fn_args = {}

                logger.info(f"[TOOL] {fn_name}({fn_args})")
                result = _execute_tool(fn_name, fn_args, session_id, self.memory, permissions)

                if isinstance(result, str) and result.startswith("ACTION_NEEDS_CONFIRMATION:"):
                    ask = result.replace("ACTION_NEEDS_CONFIRMATION:", "").strip()
                    self.memory.set_pending_action(session_id, fn_name, fn_args)
                    return ask

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": str(result),
                })

            # Second LLM call for natural-language reply
            second = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.3,
            )
            return second.choices[0].message.content or "Done."

        except openai.BadRequestError as e:
            # Groq 400 tool_use_failed — the model generated malformed tool syntax
            error_body = str(e)
            logger.warning(f"[TOOL_USE_FAILED] Groq returned 400. Attempting local parse. Error: {error_body[:300]}")

            # Try to extract the malformed tool call from the error body
            failed_gen = ""
            try:
                err_json = e.body if hasattr(e, "body") else {}
                if isinstance(err_json, dict):
                    failed_gen = err_json.get("error", {}).get("failed_generation", "")
                else:
                    # Parse from string
                    m = re.search(r"'failed_generation':\s*'([^']+)'", error_body)
                    if m:
                        failed_gen = m.group(1)
            except Exception:
                pass

            fn_name, fn_args = _parse_malformed_tool_call(failed_gen or error_body)
            if fn_name and fn_name in AVAILABLE_TOOLS:
                logger.info(f"[RECOVERED] Executing recovered tool: {fn_name}({fn_args})")
                result = _execute_tool(fn_name, fn_args or {}, session_id, self.memory, permissions)
                if isinstance(result, str) and result.startswith("ACTION_NEEDS_CONFIRMATION:"):
                    ask = result.replace("ACTION_NEEDS_CONFIRMATION:", "").strip()
                    self.memory.set_pending_action(session_id, fn_name, fn_args)
                    return ask
                return result

            # Last resort: retry as plain text without tools
            logger.info("[FALLBACK] Retrying as plain text (no tools).")
            try:
                fallback = await self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.3,
                )
                return fallback.choices[0].message.content or "I encountered an issue but I'm here to help."
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                return "I had trouble processing that request. Please try rephrasing."

        except Exception as e:
            logger.error(f"Agent error: {e}")
            err_str = str(e)
            if "429" in err_str or "insufficient_quota" in err_str.lower():
                return "API ERROR: Groq rate limit hit. Please wait a moment and try again."
            if "401" in err_str or "invalid_api_key" in err_str.lower():
                return "API ERROR: Invalid Groq API key. Please check your GROQ_API_KEY in .env."
            return f"Sorry, something went wrong. Please try again."
