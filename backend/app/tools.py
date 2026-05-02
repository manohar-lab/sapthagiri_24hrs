import json
import webbrowser

# Mock Tools for the Agent

def book_appointment(doctor: str, time: str) -> str:
    """Books a doctor appointment."""
    # In reality, this would call an external API
    return f"Successfully booked appointment with {doctor} at {time}."

def send_email(to: str, subject: str, body: str) -> str:
    """Sends an email."""
    # Mock email sending
    return f"Email sent to {to} with subject '{subject}'."

def search_info(query: str) -> str:
    """Searches the web for information."""
    # Mock search
    return f"Search results for '{query}': Example search result data."

def open_browser(query: str) -> str:
    """Opens a website or performs a Google search in the default browser."""
    import urllib.parse
    
    query = query.lower().strip()
    if "youtube" in query:
        url = "https://www.youtube.com"
        name = "YouTube"
    elif "google" in query and "search" not in query:
        url = "https://www.google.com"
        name = "Google"
    elif "." in query and " " not in query:
        url = f"https://{query}" if not query.startswith("http") else query
        name = query
    else:
        search_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={search_query}"
        name = f"Google Search for '{query}'"
        
    try:
        webbrowser.open(url)
        return f"Successfully opened {name} in your browser."
    except Exception as e:
        return f"Failed to open browser: {e}"

def update_preference(memory_store, session_id: str, key: str, value: str) -> str:
    """Updates user preference in memory."""
    memory_store.set_preference(session_id, key, value)
    return f"Preference '{key}' updated to '{value}'."

AVAILABLE_TOOLS = {
    "book_appointment": book_appointment,
    "send_email": send_email,
    "search_info": search_info,
    "open_browser": open_browser
}

# We can define OpenAI compatible schemas for these tools
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a doctor appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor": {
                        "type": "string",
                        "description": "The name of the doctor"
                    },
                    "time": {
                        "type": "string",
                        "description": "The time for the appointment"
                    }
                },
                "required": ["doctor", "time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to someone",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "The recipient's name or email"
                    },
                    "subject": {
                        "type": "string",
                        "description": "The subject of the email"
                    },
                    "body": {
                        "type": "string",
                        "description": "The body of the email"
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_preference",
            "description": "Update a user preference in memory like their name or favorite color.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The preference key (e.g., 'user_name')"
                    },
                    "value": {
                        "type": "string",
                        "description": "The preference value (e.g., 'Ravi')"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Opens a website or performs a web search in the user's default browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The name of the website (e.g. 'youtube') or a search query if it's not a specific website."
                    }
                },
                "required": ["query"]
            }
        }
    }
]
