import os
import json
import logging
from typing import List, Dict, Any
import openai

from app.memory import MemoryStore
from app.tools import AVAILABLE_TOOLS, TOOLS_SCHEMA, update_preference

logger = logging.getLogger(__name__)

class AgentController:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        # Using OpenAI client (can be pointed to a local Ollama server if needed)
        self.client = openai.AsyncOpenAI(api_key=self.api_key) if self.api_key else None
        
        self.system_prompt = """You are a highly capable agentic voice assistant.
You have access to tools to book appointments, send emails, and remember user preferences.
Always speak concisely and conversationally. You are communicating via voice.
Do not use markdown formatting like **bold** or *italics* because the user will hear your text spoken out loud.
If the user provides their name or preferences, save it using the update_user_preference tool.
If the user interrupts you or changes their mind, adapt immediately.
"""

    def get_filler(self, user_text: str) -> str:
        """Returns a quick filler word based on the user's intent to hide latency."""
        text_lower = user_text.lower()
        if "book" in text_lower or "appointment" in text_lower:
            return "Let me check the schedule for that..."
        elif "email" in text_lower or "message" in text_lower:
            return "Drafting that now..."
        elif "search" in text_lower or "find" in text_lower:
            return "Looking that up..."
        elif "name" in text_lower or "remember" in text_lower:
            return "Got it."
        # No filler for generic chat
        return ""

    async def process_message(self, session_id: str, user_text: str) -> str:
        self.memory.add_message(session_id, "user", user_text)
        
        history = self.memory.get_history(session_id)
        preferences = self.memory.get_preferences(session_id)
        
        # Build context
        pref_context = "User Preferences:\n" + "\n".join([f"{k}: {v}" for k, v in preferences.items()]) if preferences else ""
        messages = [{"role": "system", "content": self.system_prompt + "\n\n" + pref_context}]
        messages.extend(history)

        if not self.client:
            # Fallback mock agent if no API key is provided
            return self._mock_agent_response(user_text, session_id)

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini", # Fast, capable model
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.7
            )
            
            response_message = response.choices[0].message
            
            # Check if tool calls were made
            if response_message.tool_calls:
                messages.append(response_message) # Append assistant's tool call request
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {function_name} with args: {function_args}")
                    
                    if function_name == "update_user_preference":
                        tool_result = update_preference(self.memory, session_id, function_args.get("key"), function_args.get("value"))
                    elif function_name in AVAILABLE_TOOLS:
                        tool_result = AVAILABLE_TOOLS[function_name](**function_args)
                    else:
                        tool_result = f"Error: Tool {function_name} not found."
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_result
                    })
                
                # Second call to get final response after tool execution
                second_response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.7
                )
                final_text = second_response.choices[0].message.content
                self.memory.add_message(session_id, "assistant", final_text)
                return final_text
            else:
                final_text = response_message.content
                self.memory.add_message(session_id, "assistant", final_text)
                return final_text

        except Exception as e:
            logger.error(f"Agent error: {e}")
            return "Sorry, I ran into an issue while processing your request."

    def _mock_agent_response(self, text: str, session_id: str) -> str:
        text = text.lower()
        if "book" in text:
            reply = AVAILABLE_TOOLS["book_appointment"]("Dr. Smith", "tomorrow 5 PM")
        elif "email" in text:
            reply = AVAILABLE_TOOLS["send_email"]("boss@company.com", "Running late", "I will be late today.")
        elif "name is" in text:
            name = text.split("name is")[-1].strip()
            update_preference(self.memory, session_id, "user_name", name)
            reply = f"Nice to meet you, {name}. I will remember that."
        elif "open" in text:
            query = text.split("open", 1)[-1].strip()
            reply = AVAILABLE_TOOLS["open_browser"](query)
        else:
            reply = "I understand. I am running in offline mock mode right now."
        
        self.memory.add_message(session_id, "assistant", reply)
        return reply
