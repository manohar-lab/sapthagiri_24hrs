import json
import webbrowser
import os
import datetime
import subprocess
import time
import platform
from ctypes import cast, POINTER
from typing import Optional, Dict, Any
import logging
from urllib.parse import quote

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

# NOTE: pywhatkit is intentionally NOT imported at the top level.
# It creates a Flask("app") on import which conflicts with our FastAPI "app" module name.
# It is lazy-imported inside send_whatsapp() to avoid this.

# ── Risk Levels for Safety Layer ─────────────────────────────────────────────

RISK_LEVELS = {
    'LOW': ['take_screenshot', 'control_volume', 'open_browser', 'search_info', 'get_clipboard'],
    'MEDIUM': ['launch_app', 'type_text', 'press_keys', 'set_clipboard', 'close_app', 'undo_last_action'],
    'HIGH': ['send_whatsapp', 'send_email', 'browser_automation', 'execute_system_command']
}

TOOL_POLICIES = {
    "send_whatsapp": {"requires_confirmation": True, "undo_hint": "Not undoable once sent."},
    "close_app": {"requires_confirmation": True, "undo_hint": "Re-open the app manually."},
    "browser_automation": {"requires_confirmation_for": ["fill", "submit"]},
    "type_text": {"undo_hint": "Say 'press Ctrl+Z' or use undo_last_action."},
    "set_clipboard": {"undo_hint": "Clipboard can be restored if previous text is known."},
}

_LAST_CLIPBOARD = ""

def get_risk_level(tool_name: str) -> str:
    """Returns the risk level of a tool."""
    for level, tools in RISK_LEVELS.items():
        if tool_name in tools:
            return level
    return 'MEDIUM'  # Default to medium if unknown


def requires_confirmation(tool_name: str, args: Optional[Dict[str, Any]] = None) -> bool:
    """Centralized safety rule check for sensitive actions."""
    args = args or {}
    policy = TOOL_POLICIES.get(tool_name, {})
    if policy.get("requires_confirmation"):
        return True
    if tool_name == "browser_automation" and args.get("action") in policy.get("requires_confirmation_for", []):
        return True
    return False


def get_undo_hint(tool_name: str) -> Optional[str]:
    policy = TOOL_POLICIES.get(tool_name, {})
    return policy.get("undo_hint")

# ── Tools ────────────────────────────────────────────────────────────────────

def book_appointment(doctor: str, time: str) -> str:
    """Books a doctor appointment (mock)."""
    return f"Successfully booked appointment with {doctor} at {time}."

def send_email(to: str, subject: str, body: str) -> str:
    """Sends an email (mock)."""
    return f"Email sent to {to} with subject '{subject}'."

def search_info(query: str) -> str:
    """Searches the web for information (mock)."""
    return f"Search results for '{query}': Example search result data."

# ── Site-specific search URL builders ────────────────────────────────────────

SITE_SEARCH_URLS = {
    "flipkart": "https://www.flipkart.com/search?q={query}",
    "amazon": "https://www.amazon.in/s?k={query}",
    "amazon india": "https://www.amazon.in/s?k={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "google": "https://www.google.com/search?q={query}",
    "meesho": "https://www.meesho.com/search?q={query}",
    "myntra": "https://www.myntra.com/{query}",
    "snapdeal": "https://www.snapdeal.com/search?keyword={query}",
    "nykaa": "https://www.nykaa.com/search/result/?q={query}",
    "swiggy": "https://www.swiggy.com/search?query={query}",
    "zomato": "https://www.zomato.com/search?q={query}",
    "github": "https://github.com/search?q={query}",
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={query}",
    "twitter": "https://twitter.com/search?q={query}",
    "x": "https://x.com/search?q={query}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "ebay": "https://www.ebay.com/sch/i.html?_nkw={query}",
    "blinkit": "https://blinkit.com/s/?q={query}",
    "bigbasket": "https://www.bigbasket.com/ps/?q={query}",
}

SITE_HOME_URLS = {
    "flipkart": "https://www.flipkart.com",
    "amazon": "https://www.amazon.in",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "meesho": "https://www.meesho.com",
    "myntra": "https://www.myntra.com",
    "snapdeal": "https://www.snapdeal.com",
    "nykaa": "https://www.nykaa.com",
    "swiggy": "https://www.swiggy.com",
    "zomato": "https://www.zomato.com",
    "github": "https://github.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "ebay": "https://www.ebay.com",
    "netflix": "https://www.netflix.com",
    "hotstar": "https://www.hotstar.com",
    "primevideo": "https://www.primevideo.com",
    "spotify": "https://open.spotify.com",
    "whatsapp": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com",
    "outlook": "https://outlook.live.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
}


def search_on_site(site: str, query: str) -> str:
    """
    Searches for a query on a specific website (e.g., Flipkart, Amazon, YouTube).
    Constructs the correct search URL and opens it in the default browser.
    """
    import urllib.parse
    site_key = site.lower().strip()
    encoded_query = urllib.parse.quote(query)

    # Check if we have a known search URL template for this site
    search_template = SITE_SEARCH_URLS.get(site_key)
    if search_template:
        url = search_template.replace("{query}", encoded_query)
        display_name = site.title()
    else:
        # Fallback: Google search scoped to the site
        url = f"https://www.google.com/search?q=site:{site_key}.com+{encoded_query}"
        display_name = site.title()

    try:
        webbrowser.open(url)
        logger.info(f"Opened search: {url}")
        return f"Searching for '{query}' on {display_name}. Opening results now."
    except Exception as e:
        logger.error(f"search_on_site failed: {e}")
        return f"Failed to open search: {e}"


def open_browser(query: str) -> str:
    """Opens a website or performs a Google/site search in the default browser."""
    import urllib.parse
    import re
    raw = query.strip()
    lower = raw.lower()

    # Detect "search for X on SITE" or "search X on SITE" patterns
    match = re.search(
        r'search(?:\s+for)?\s+(.+?)\s+on\s+([a-z0-9 ]+)',
        lower
    )
    if match:
        search_query = match.group(1).strip()
        site_name = match.group(2).strip()
        return search_on_site(site_name, search_query)

    # Detect "open SITE and search for X" pattern
    match2 = re.search(
        r'open\s+([a-z0-9 ]+?)\s+and\s+search(?:\s+for)?\s+(.+)',
        lower
    )
    if match2:
        site_name = match2.group(1).strip()
        search_query = match2.group(2).strip()
        return search_on_site(site_name, search_query)

    # Check for known site home pages
    for site_key, home_url in SITE_HOME_URLS.items():
        if site_key in lower and len(lower.split()) <= 3:
            try:
                webbrowser.open(home_url)
                return f"Successfully opened {site_key.title()} in your browser."
            except Exception as e:
                return f"Failed to open browser: {e}"

    # Plain URL
    if "." in raw and " " not in raw:
        url = f"https://{raw}" if not raw.startswith("http") else raw
        try:
            webbrowser.open(url)
            return f"Successfully opened {raw} in your browser."
        except Exception as e:
            return f"Failed to open browser: {e}"

    # Google search fallback
    url = f"https://www.google.com/search?q={urllib.parse.quote(raw)}"
    try:
        webbrowser.open(url)
        return f"Searching Google for '{raw}'."
    except Exception as e:
        return f"Failed to open browser: {e}"

def update_preference(memory_store, session_id: str, key: str, value: str) -> str:
    """Updates user preference in memory."""
    memory_store.set_preference(session_id, key, value)
    return f"Preference '{key}' updated to '{value}'."

def take_screenshot(region: Optional[str] = None) -> str:
    """Takes a screenshot and saves it locally. Optionally specify region as 'x,y,width,height'."""
    try:
        import pyautogui
        os.makedirs("screenshots", exist_ok=True)
        filename = f"screenshots/screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        if region:
            # Parse region: "100,100,800,600"
            x, y, w, h = map(int, region.split(','))
            screenshot = pyautogui.screenshot(region=(x, y, w, h))
        else:
            screenshot = pyautogui.screenshot()
        
        screenshot.save(filename)
        abs_path = os.path.abspath(filename)
        logger.info(f"Screenshot saved: {abs_path}")
        return f"Screenshot saved successfully at {abs_path}"
    except ImportError:
        return "Screenshot library (pyautogui) not installed. Run: pip install pyautogui"
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return f"Failed to take screenshot: {e}"

def control_volume(action: str, percent: int = 10, level: float = None) -> str:
    """Controls system volume. Action: 'increase', 'decrease', 'mute', or 'set' (with percent or level 0.0-1.0)."""
    try:
        system = platform.system().lower()
        if system == "windows":
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

            if action == "mute":
                current_mute = volume.GetMute()
                volume.SetMute(0 if current_mute else 1, None)
                state = "unmuted" if current_mute else "muted"
                return f"Volume {state}."

            current_vol = volume.GetMasterVolumeLevelScalar()
            if level is not None:
                volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level)), None)
                return f"Volume set to {int(level*100)}%."
            
            if action == "increase":
                volume.SetMasterVolumeLevelScalar(min(1.0, current_vol + percent / 100), None)
                return f"Increased volume by {percent}%."
            if action == "decrease":
                volume.SetMasterVolumeLevelScalar(max(0.0, current_vol - percent / 100), None)
                return f"Decreased volume by {percent}%."
            if action == "set":
                volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, percent / 100)), None)
                return f"Volume set to {percent}%."
            return "Unknown volume action."

        if system == "darwin":
            if action == "mute":
                subprocess.run(["osascript", "-e", "set volume output muted true"], check=False)
                return "Volume muted."
            if action == "set":
                subprocess.run(["osascript", "-e", f"set volume output volume {max(0, min(100, percent))}"], check=False)
                return f"Volume set to {percent}%."
            delta = max(1, percent)
            op = "+" if action == "increase" else "-"
            script = f"set volume output volume ((output volume of (get volume settings)) {op} {delta})"
            subprocess.run(["osascript", "-e", script], check=False)
            return f"Volume {action}d by {percent}%."

        # Linux fallback
        if action == "mute":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "toggle"], check=False)
            return "Toggled mute."
        if action in ("increase", "decrease"):
            sign = "+" if action == "increase" else "-"
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%{sign}"], check=False)
            return f"Volume {action}d by {percent}%."
        if action == "set":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"], check=False)
            return f"Volume set to {percent}%."
        return "Unknown volume action. Use: increase, decrease, mute, or set."
    except ImportError:
        return "Volume control libraries (pycaw/comtypes) not installed. Run: pip install pycaw comtypes"
    except Exception as e:
        logger.error(f"Volume control failed: {e}")
        return f"Failed to control volume: {e}"

def open_app(app_name: str) -> str:
    """Launches an application by name on Windows."""
    try:
        app_lower = app_name.lower().strip()
        
        # Common application mappings
        app_map = {
            'chrome': 'chrome.exe',
            'google chrome': 'chrome.exe',
            'firefox': 'firefox.exe',
            'edge': 'msedge.exe',
            'microsoft edge': 'msedge.exe',
            'vscode': 'code',
            'notepad': 'notepad.exe',
            'calculator': 'calc.exe',
            'calc': 'calc.exe',
            'paint': 'mspaint.exe',
            'explorer': 'explorer.exe',
            'file explorer': 'explorer.exe',
            'settings': 'ms-settings:',
            'control panel': 'control',
            'cmd': 'cmd.exe',
            'powershell': 'powershell.exe',
            'terminal': 'wt.exe',
            'spotify': 'spotify.exe',
            'discord': 'discord.exe',
            'task manager': 'taskmgr.exe',
            'word': 'winword.exe',
            'microsoft word': 'winword.exe',
            'excel': 'excel.exe',
            'powerpoint': 'powerpnt.exe',
        }
        
        target = app_map.get(app_lower, app_name.strip())
        
        # Try to launch
        if platform.system().lower() == "windows":
            import os
            import subprocess
            try:
                # os.startfile is more reliable for URI schemes and installed apps
                os.startfile(target)
            except Exception:
                # Robust fallback for Settings and URI schemes
                subprocess.Popen(f'start "" "{target}"', shell=True)
        else:
            subprocess.Popen([target], shell=False)
            
        logger.info(f"Launched app: {app_name} (target: {target})")
        return f"{app_name} has been launched successfully."
    except Exception as e:
        logger.error(f"App launch failed: {e}")
        return f"Failed to launch app '{app_name}': {e}"

def open_file(path: str) -> str:
    """Opens a specific file or folder path."""
    try:
        import os
        import platform
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"Error: The path '{path}' does not exist."
            
        if platform.system().lower() == "windows":
            os.startfile(abs_path)
        else:
            subprocess.Popen(["open" if platform.system().lower() == "darwin" else "xdg-open", abs_path])
            
        return f"Opened file/folder: {abs_path}"
    except Exception as e:
        return f"Failed to open file: {e}"


def close_app(app_name: str, confirmed: bool = False) -> str:
    """Closes a running application. Requires confirmation."""
    if not confirmed:
        return f"ACTION_NEEDS_CONFIRMATION: Do you want to close {app_name}? This will terminate the application."
    
    try:
        app_lower = app_name.lower()
        
        # Process name mappings
        process_map = {
            'chrome': 'chrome.exe',
            'google chrome': 'chrome.exe',
            'firefox': 'firefox.exe',
            'edge': 'msedge.exe',
            'microsoft edge': 'msedge.exe',
            'code': 'Code.exe',
            'vscode': 'Code.exe',
            'notepad': 'notepad.exe',
            'calculator': 'Calculator.exe',
            'calc': 'Calculator.exe',
            'paint': 'mspaint.exe',
            'spotify': 'Spotify.exe',
            'discord': 'Discord.exe',
            'slack': 'slack.exe',
        }
        
        process_name = process_map.get(app_lower, f"{app_name}.exe")
        
        # Kill the process
        result = subprocess.run(['taskkill', '/F', '/IM', process_name], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Closed app: {app_name}")
            return f"Successfully closed {app_name}."
        else:
            return f"Could not find running instance of {app_name}."
    except Exception as e:
        logger.error(f"App close failed: {e}")
        return f"Failed to close app: {e}"

def type_text(text: str, press_enter: bool = False) -> str:
    """Types text into the active window using keyboard automation."""
    try:
        import pyautogui
        
        # Small delay to ensure window is focused
        time.sleep(0.5)
        
        pyautogui.write(text, interval=0.01)
        
        if press_enter:
            pyautogui.press('enter')
        
        logger.info(f"Typed text: {text[:50]}...")
        return f"Successfully typed text{' and pressed Enter' if press_enter else ''}."
    except ImportError:
        return "Keyboard automation library (pyautogui) not installed. Run: pip install pyautogui"
    except Exception as e:
        logger.error(f"Type text failed: {e}")
        return f"Failed to type text: {e}"


def press_keys(keys: str) -> str:
    """Presses keyboard keys or key combinations. Examples: 'enter', 'ctrl+c', 'alt+tab'."""
    try:
        import pyautogui
        
        # Parse key combination
        if '+' in keys:
            key_list = [k.strip().lower() for k in keys.split('+')]
            pyautogui.hotkey(*key_list)
            logger.info(f"Pressed keys: {keys}")
            return f"Successfully pressed {keys}."
        else:
            pyautogui.press(keys.lower())
            logger.info(f"Pressed key: {keys}")
            return f"Successfully pressed {keys}."
    except ImportError:
        return "Keyboard automation library (pyautogui) not installed. Run: pip install pyautogui"
    except Exception as e:
        logger.error(f"Press keys failed: {e}")
        return f"Failed to press keys: {e}"


def get_clipboard() -> str:
    """Gets the current clipboard content."""
    try:
        import pyperclip
        content = pyperclip.paste()
        logger.info("Retrieved clipboard content")
        return f"Clipboard content: {content}"
    except ImportError:
        return "Clipboard library (pyperclip) not installed. Run: pip install pyperclip"
    except Exception as e:
        logger.error(f"Get clipboard failed: {e}")
        return f"Failed to get clipboard: {e}"


def set_clipboard(text: str) -> str:
    """Sets the clipboard content."""
    try:
        import pyperclip
        global _LAST_CLIPBOARD
        _LAST_CLIPBOARD = pyperclip.paste()
        pyperclip.copy(text)
        logger.info(f"Set clipboard: {text[:50]}...")
        return f"Successfully copied to clipboard."
    except ImportError:
        return "Clipboard library (pyperclip) not installed. Run: pip install pyperclip"
    except Exception as e:
        logger.error(f"Set clipboard failed: {e}")
        return f"Failed to set clipboard: {e}"


def undo_last_action(action_hint: str = "auto") -> str:
    """
    Best-effort undo support.
    - "clipboard": restore previous clipboard state
    - "typing"/"auto": send Ctrl+Z
    """
    try:
        if action_hint == "clipboard":
            import pyperclip
            pyperclip.copy(_LAST_CLIPBOARD)
            return "Restored previous clipboard content."
        import pyautogui
        pyautogui.hotkey("ctrl", "z")
        return "Sent Ctrl+Z to undo last UI action."
    except Exception as e:
        return f"Undo failed: {e}"


def send_whatsapp(contact: str, message: str, confirmed: bool = False, mode: str = "real") -> str:
    """
    Sends a WhatsApp message. Requires explicit user confirmation first.
    
    Args:
        contact: Contact name or phone number (with country code, e.g., +91XXXXXXXXXX)
        message: Message to send
        confirmed: Must be True after user confirms
        mode: 'real' for actual sending (default), 'demo' for simulation
    """
    if not confirmed:
        is_phone = contact.startswith('+') and any(ch.isdigit() for ch in contact)
        if not is_phone:
            return (
                f"ACTION_NEEDS_CONFIRMATION: I need a phone number to send a WhatsApp message. "
                f"Please provide the phone number for '{contact}' with country code "
                f"(e.g., +91XXXXXXXXXX), then I will send: '{message}'."
            )
        return f"ACTION_NEEDS_CONFIRMATION: Do you want to send WhatsApp message to {contact}: '{message}'?"

    try:
        if mode == "demo":
            logger.info(f"[DEMO] WhatsApp to {contact}: {message}")
            return f"✓ Demo Mode: Simulated sending WhatsApp message to '{contact}' saying '{message}'."

        # ── Real Mode ────────────────────────────────────────────────────────
        is_phone = contact.startswith('+') and any(ch.isdigit() for ch in contact)

        if is_phone:
            # Direct send via pywhatkit (most reliable, no browser needed)
            import pywhatkit
            import datetime
            now = datetime.datetime.now()
            # Schedule 1 minute from now to give pywhatkit time to open the browser
            send_hour = now.hour
            send_min = now.minute + 1
            if send_min >= 60:
                send_min -= 60
                send_hour = (send_hour + 1) % 24

            pywhatkit.sendwhatmsg(
                phone_no=contact,
                message=message,
                time_hour=send_hour,
                time_min=send_min,
                wait_time=20,
                tab_close=True,
                close_time=5,
            )
            logger.info(f"WhatsApp sent via pywhatkit to {contact}")
            return f"✓ Successfully sent WhatsApp message to {contact}."

        else:
            # Contact name: use Selenium to search on WhatsApp Web
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            import os
            import time

            options = Options()
            options.add_argument("--user-data-dir=" + os.path.expanduser("~") + r"\AppData\Local\Google\Chrome\User Data")
            options.add_argument("--profile-directory=Default")
            options.add_experimental_option("detach", True)

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            wait = WebDriverWait(driver, 60)
            driver.get("https://web.whatsapp.com/")

            # Wait for WhatsApp Web to load (QR scan or already logged in)
            search_box = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@contenteditable='true'][@data-tab='3']")
                )
            )
            search_box.click()
            time.sleep(0.5)
            search_box.send_keys(contact)
            time.sleep(2)

            # Click the first matching contact
            first_result = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//span[@title='{contact}']")
                )
            )
            first_result.click()
            time.sleep(1)

            # Type and send the message
            msg_box = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@contenteditable='true'][@data-tab='10']")
                )
            )
            msg_box.click()
            msg_box.send_keys(message)
            time.sleep(0.5)
            msg_box.send_keys(Keys.ENTER)
            time.sleep(2)
            driver.quit()

            logger.info(f"WhatsApp sent via Selenium to contact '{contact}'")
            return f"✓ Successfully sent WhatsApp message to '{contact}' via WhatsApp Web."

    except ImportError as e:
        return f"Required library not installed: {e}. Run: pip install pywhatkit selenium webdriver-manager"
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
def browser_automation(action: str, url: Optional[str] = None, selector: Optional[str] = None, 
                       text: Optional[str] = None, confirmed: bool = False) -> str:
    """
    Automates browser actions using Selenium.
    
    Args:
        action: 'open', 'click', 'fill', 'submit'
        url: URL to open (for 'open' action)
        selector: CSS selector for element (for 'click', 'fill' actions)
        text: Text to fill (for 'fill' action)
        confirmed: Confirmation for sensitive actions
    """
    if not confirmed and action in ['fill', 'submit']:
        return f"ACTION_NEEDS_CONFIRMATION: Do you want to perform browser automation: {action}?"
    
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        wait = WebDriverWait(driver, 20)

        if action == "open":
            if not url:
                return "URL required for 'open' action."
            driver.get(url)
            logger.info(f"Browser opened: {url}")
            return f"Opened {url} in browser."

        if not selector:
            return "Selector is required for click/fill/submit actions."

        if action == "click":
            element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            element.click()
            return f"Clicked element: {selector}"

        if action == "fill":
            element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            element.clear()
            element.send_keys(text or "")
            return f"Filled element {selector}"

        if action == "submit":
            element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            element.submit()
            return f"Submitted form using {selector}"

        return "Unsupported browser action."
            
    except ImportError:
        return "Selenium not installed. Run: pip install selenium"
    except Exception as e:
        logger.error(f"Browser automation failed: {e}")
        return f"Browser automation failed: {e}"

def move_mouse(x: int, y: int) -> str:
    """Moves the mouse cursor to specific X, Y coordinates."""
    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=0.5)
        return f"Moved mouse to ({x}, {y})"
    except Exception as e:
        return f"Failed to move mouse: {e}"

def click_mouse(button: str = 'left') -> str:
    """Clicks the mouse. Button can be 'left', 'right', or 'middle'."""
    try:
        import pyautogui
        pyautogui.click(button=button)
        return f"Performed {button} mouse click."
    except Exception as e:
        return f"Failed to click mouse: {e}"

# ── Tool registry ─────────────────────────────────────────────────────────────

AVAILABLE_TOOLS = {
    "book_appointment": book_appointment,
    "send_email": send_email,
    "search_info": search_info,
    "open_browser": open_browser,
    "search_on_site": search_on_site,
    "take_screenshot": take_screenshot,
    "control_volume": control_volume,
    "open_app": open_app,
    "open_file": open_file,
    "close_app": close_app,
    "type_text": type_text,
    "press_keys": press_keys,
    "get_clipboard": get_clipboard,
    "set_clipboard": set_clipboard,
    "undo_last_action": undo_last_action,
    "send_whatsapp": send_whatsapp,
    "browser_automation": browser_automation,
    "move_mouse": move_mouse,
    "click_mouse": click_mouse,
}

# ── OpenAI-compatible function schemas ────────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a doctor appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor": {"type": "string", "description": "Name of the doctor"},
                    "time": {"type": "string", "description": "Appointment time"}
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
                    "to": {"type": "string", "description": "Recipient name or email"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body"}
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_preference",
            "description": "Save a user preference like their name or favourite anything.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Preference key, e.g. 'user_name'"},
                    "value": {"type": "string", "description": "Preference value, e.g. 'Ravi'"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Opens a website or performs a Google search. Also handles 'search for X on SITE' patterns automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Website name, URL, or search query (e.g. 'flipkart', 'search for laptop on amazon')"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_on_site",
            "description": "Searches for something on a specific website like Flipkart, Amazon, YouTube, Meesho, Myntra, etc. Use this when the user says 'search for X on Flipkart' or 'find laptops on Amazon' or 'search YouTube for music'. This is the PRIMARY tool for in-site searches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {
                        "type": "string",
                        "description": "The website to search on (e.g., 'flipkart', 'amazon', 'youtube', 'meesho', 'myntra', 'snapdeal')"
                    },
                    "query": {
                        "type": "string",
                        "description": "The search term to look for (e.g., 'laptop', 'red dress', 'hindi songs')"
                    }
                },
                "required": ["site", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Takes a screenshot and saves it locally. Can capture full screen or a specific region.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "Optional region as 'x,y,width,height' (e.g., '100,100,800,600')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_volume",
            "description": "Controls the system audio volume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["increase", "decrease", "mute", "set"],
                        "description": "Volume action: increase, decrease, mute, or set to specific level"
                    },
                    "percent": {
                        "type": "integer",
                        "description": "Percentage change (for increase/decrease) or target level (for set). Default: 10"
                    },
                    "level": {
                        "type": "number",
                        "description": "Direct volume level from 0.0 (mute) to 1.0 (max). Use this if user specifies a specific level."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Launches a desktop application (e.g., chrome, firefox, vscode, notepad, calculator, spotify, discord).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Name of the application to launch"}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Closes a running application. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Name of the application to close"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true ONLY after user confirms. Always start with false."
                    }
                },
                "required": ["app_name", "confirmed"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Automates typing text into the currently active window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "press_enter": {
                        "type": "boolean",
                        "description": "Press Enter after typing. Default: false"
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_keys",
            "description": "Presses keyboard keys or key combinations. Examples: 'enter', 'ctrl+c', 'alt+tab', 'win+d'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "Key or key combination (use + for combinations, e.g., 'ctrl+c')"
                    }
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard",
            "description": "Gets the current clipboard content.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_clipboard",
            "description": "Sets the clipboard content (copy to clipboard).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to copy to clipboard"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "undo_last_action",
            "description": "Best-effort undo for last operation (typing or clipboard restore).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_hint": {
                        "type": "string",
                        "enum": ["auto", "typing", "clipboard"],
                        "description": "Optional hint about what should be undone."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp",
            "description": "Sends a WhatsApp message. Always requires user confirmation. Supports demo and real modes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact": {
                        "type": "string",
                        "description": "Contact name or phone number with country code (e.g., +1234567890)"
                    },
                    "message": {"type": "string", "description": "Message to send"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true ONLY after user explicitly confirms. Always start with false."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["demo", "real"],
                        "description": "Mode: 'real' for actual sending (default), 'demo' for simulation. Default: real"
                    }
                },
                "required": ["contact", "message", "confirmed"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_automation",
            "description": "Automates browser actions like opening URLs, clicking elements, filling forms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["open", "click", "fill", "submit"],
                        "description": "Browser action to perform"
                    },
                    "url": {"type": "string", "description": "URL to open (required for 'open' action)"},
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for element (for 'click', 'fill' actions)"
                    },
                    "text": {"type": "string", "description": "Text to fill (for 'fill' action)"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Confirmation for sensitive actions. Default: false"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_mouse",
            "description": "Moves the mouse cursor to specific X, Y coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_mouse",
            "description": "Clicks the mouse (left, right, or middle).",
            "parameters": {
                "type": "object",
                "properties": {
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button to click. Default: left"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_file",
            "description": "Opens a specific file or folder path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute or relative path to the file or folder."
                    }
                },
                "required": ["path"]
            }
        }
    }
]
