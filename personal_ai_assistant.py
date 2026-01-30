#!/usr/bin/env python3
"""
Personal AI Assistant for macOS
Author: YS
Version: 1.0.0

A personal AI assistant that runs on your Mac and can be controlled via Telegram.
Features:
- AI-powered chat (Claude API / OpenAI API / Local Ollama)
- Mac system control (apps, files, settings)
- Screenshot capture and sharing
- File management and search
- Reminders and notes
- Web search
- System monitoring
- And more...

Setup:
1. Install dependencies: pip3 install python-telegram-bot anthropic aiohttp
2. Get Telegram Bot Token from @BotFather
3. Get your Telegram User ID from @userinfobot
4. Set environment variables or edit config below
5. Run: python3 personal_ai_assistant.py

Security: Only responds to your Telegram user ID (owner-only mode)
"""

import os
import sys
import json
import asyncio
import logging
import subprocess
import platform
import hashlib
import base64
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from functools import wraps
import urllib.request
import urllib.parse

# ============================================================================
# CONFIGURATION - Edit these or use environment variables
# ============================================================================

def get_owner_id():
    """Safely get owner ID from environment."""
    val = os.getenv("TELEGRAM_OWNER_ID", "0")
    try:
        return int(val)
    except ValueError:
        print(f"\n[ERROR] TELEGRAM_OWNER_ID must be a number, got: '{val}'")
        print("\nTo get your Telegram User ID:")
        print("1. Open Telegram")
        print("2. Search for @userinfobot")
        print("3. Start a chat - it will reply with your numeric ID")
        print("\nThen set it correctly:")
        print("  export TELEGRAM_OWNER_ID=123456789")
        print("")
        return 0

CONFIG = {
    # Telegram Configuration
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE"),
    "TELEGRAM_OWNER_ID": get_owner_id(),  # Your Telegram user ID (number)

    # AI Provider: "claude", "openai", or "ollama"
    "AI_PROVIDER": os.getenv("AI_PROVIDER", "claude"),

    # Claude API
    "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "YOUR_CLAUDE_API_KEY"),
    "CLAUDE_MODEL": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),

    # OpenAI API (alternative)
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
    "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4"),

    # Ollama (local, free)
    "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "llama3"),
    "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "http://localhost:11434"),

    # Assistant Configuration
    "ASSISTANT_NAME": os.getenv("ASSISTANT_NAME", "Jarvis"),
    "MAX_HISTORY": int(os.getenv("MAX_HISTORY", "20")),

    # Paths
    "DATA_DIR": Path.home() / ".personal_ai_assistant",
    "SCREENSHOTS_DIR": Path.home() / "Desktop" / "AI_Screenshots",
}

# System prompt for the AI
SYSTEM_PROMPT = """You are {name}, a personal AI assistant running on {owner}'s Mac.
You are helpful, smart, and can execute commands on the Mac system.

Current time: {time}
System: macOS {os_version}

You have access to these capabilities (use them when appropriate):
- /screenshot - Take a screenshot
- /apps - List running applications
- /open <app> - Open an application
- /close <app> - Close an application
- /files <path> - List files in directory
- /search <query> - Search files on Mac
- /system - Show system info
- /battery - Show battery status
- /wifi - Show WiFi info
- /volume <0-100> - Set volume
- /brightness <0-100> - Set brightness
- /notify <message> - Show Mac notification
- /clipboard - Get clipboard content
- /clipboard <text> - Set clipboard content
- /reminder <time> <message> - Set a reminder
- /notes - List notes
- /note <title> <content> - Save a note
- /web <query> - Search the web
- /download <url> - Download a file
- /shell <command> - Execute shell command (careful!)

When the user asks you to do something on their Mac, use these commands.
Be conversational and helpful. You're their personal assistant!
"""

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PersonalAI")

# ============================================================================
# DATABASE FOR NOTES, REMINDERS, HISTORY
# ============================================================================

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS commands_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    # Notes
    def add_note(self, title: str, content: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title, content))
        self.conn.commit()
        return cursor.lastrowid

    def get_notes(self, limit: int = 10) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, content, created_at FROM notes ORDER BY created_at DESC LIMIT ?", (limit,))
        return [{"id": r[0], "title": r[1], "content": r[2], "created_at": r[3]} for r in cursor.fetchall()]

    def delete_note(self, note_id: int):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self.conn.commit()

    # Reminders
    def add_reminder(self, message: str, remind_at: datetime) -> int:
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO reminders (message, remind_at) VALUES (?, ?)", (message, remind_at))
        self.conn.commit()
        return cursor.lastrowid

    def get_pending_reminders(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, message, remind_at FROM reminders WHERE completed = 0 AND remind_at <= ? ORDER BY remind_at",
            (datetime.now(),)
        )
        return [{"id": r[0], "message": r[1], "remind_at": r[2]} for r in cursor.fetchall()]

    def complete_reminder(self, reminder_id: int):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,))
        self.conn.commit()

    # Chat History
    def add_message(self, role: str, content: str):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
        self.conn.commit()

    def get_history(self, limit: int = 20) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT role, content FROM chat_history ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [{"role": r[0], "content": r[1]} for r in reversed(cursor.fetchall())]

    def clear_history(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chat_history")
        self.conn.commit()

    def log_command(self, command: str, result: str):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO commands_log (command, result) VALUES (?, ?)", (command, result))
        self.conn.commit()

# ============================================================================
# MAC SYSTEM CONTROLLER
# ============================================================================

class MacController:
    """Controls Mac system functions via AppleScript and shell commands."""

    @staticmethod
    def run_applescript(script: str) -> str:
        """Run an AppleScript and return the result."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip() or result.stderr.strip()
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {str(e)}"

    @staticmethod
    def run_shell(command: str, timeout: int = 30) -> str:
        """Run a shell command and return the result."""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout.strip() or result.stderr.strip()
            return output[:4000] if output else "Command executed successfully"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out"
        except Exception as e:
            return f"Error: {str(e)}"

    # Screenshots
    def take_screenshot(self, save_path: Path = None) -> Path:
        """Take a screenshot and return the file path."""
        if save_path is None:
            CONFIG["SCREENSHOTS_DIR"].mkdir(parents=True, exist_ok=True)
            save_path = CONFIG["SCREENSHOTS_DIR"] / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        self.run_shell(f"screencapture -x '{save_path}'")
        return save_path

    # Applications
    def get_running_apps(self) -> List[str]:
        """Get list of running applications."""
        script = 'tell application "System Events" to get name of every process whose background only is false'
        result = self.run_applescript(script)
        return [app.strip() for app in result.split(", ")] if result else []

    def open_app(self, app_name: str) -> str:
        """Open an application."""
        return self.run_applescript(f'tell application "{app_name}" to activate')

    def close_app(self, app_name: str) -> str:
        """Close an application."""
        return self.run_applescript(f'tell application "{app_name}" to quit')

    # Files
    def list_files(self, path: str = "~") -> List[str]:
        """List files in a directory."""
        expanded_path = os.path.expanduser(path)
        try:
            items = os.listdir(expanded_path)
            return sorted(items)[:50]  # Limit to 50 items
        except Exception as e:
            return [f"Error: {str(e)}"]

    def search_files(self, query: str, path: str = "~") -> List[str]:
        """Search for files using mdfind (Spotlight)."""
        expanded_path = os.path.expanduser(path)
        result = self.run_shell(f"mdfind -onlyin '{expanded_path}' '{query}' | head -20")
        return result.split("\n") if result else []

    # System Info
    def get_system_info(self) -> Dict:
        """Get system information."""
        info = {
            "hostname": platform.node(),
            "os": platform.system(),
            "os_version": platform.mac_ver()[0],
            "architecture": platform.machine(),
            "python": platform.python_version(),
        }

        # CPU info
        cpu_info = self.run_shell("sysctl -n machdep.cpu.brand_string")
        info["cpu"] = cpu_info

        # Memory
        mem_info = self.run_shell("sysctl -n hw.memsize")
        try:
            mem_gb = int(mem_info) / (1024**3)
            info["memory"] = f"{mem_gb:.1f} GB"
        except:
            info["memory"] = "Unknown"

        # Disk
        disk_info = self.run_shell("df -h / | tail -1 | awk '{print $4}'")
        info["disk_free"] = disk_info

        return info

    def get_battery_status(self) -> Dict:
        """Get battery status."""
        result = self.run_shell("pmset -g batt")
        info = {"raw": result}

        # Parse battery percentage
        match = re.search(r'(\d+)%', result)
        if match:
            info["percentage"] = int(match.group(1))

        # Check if charging
        info["charging"] = "AC Power" in result or "charging" in result.lower()

        return info

    def get_wifi_info(self) -> Dict:
        """Get WiFi information."""
        result = self.run_shell("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I")
        info = {"raw": result}

        for line in result.split("\n"):
            if "SSID:" in line and "BSSID" not in line:
                info["ssid"] = line.split(":")[1].strip()
            elif "agrCtlRSSI:" in line:
                info["signal"] = line.split(":")[1].strip()

        return info

    # Audio/Display
    def set_volume(self, level: int) -> str:
        """Set system volume (0-100)."""
        level = max(0, min(100, level))
        # Convert to 0-7 scale for AppleScript
        vol = int(level * 7 / 100)
        return self.run_applescript(f"set volume {vol}")

    def get_volume(self) -> int:
        """Get current volume level."""
        result = self.run_applescript("output volume of (get volume settings)")
        try:
            return int(result)
        except:
            return 0

    def set_brightness(self, level: int) -> str:
        """Set screen brightness (0-100)."""
        level = max(0, min(100, level))
        brightness = level / 100
        return self.run_shell(f"brightness {brightness}")

    # Notifications
    def send_notification(self, message: str, title: str = "AI Assistant") -> str:
        """Send a macOS notification."""
        script = f'display notification "{message}" with title "{title}"'
        return self.run_applescript(script)

    # Clipboard
    def get_clipboard(self) -> str:
        """Get clipboard contents."""
        return self.run_shell("pbpaste")

    def set_clipboard(self, text: str) -> str:
        """Set clipboard contents."""
        # Use AppleScript to avoid shell escaping issues
        script = f'set the clipboard to "{text}"'
        return self.run_applescript(script)

    # Say (Text to Speech)
    def say(self, text: str, voice: str = "Samantha") -> str:
        """Speak text using macOS TTS."""
        return self.run_shell(f"say -v {voice} '{text}'")

# ============================================================================
# AI ENGINE
# ============================================================================

class AIEngine:
    """Handles AI conversations using various providers."""

    def __init__(self, provider: str = "claude"):
        self.provider = provider
        self.conversation_history = []

    async def chat(self, message: str, system_prompt: str = "") -> str:
        """Send a message and get a response."""
        if self.provider == "claude":
            return await self._chat_claude(message, system_prompt)
        elif self.provider == "openai":
            return await self._chat_openai(message, system_prompt)
        elif self.provider == "ollama":
            return await self._chat_ollama(message, system_prompt)
        else:
            return "Error: Unknown AI provider"

    async def _chat_claude(self, message: str, system_prompt: str) -> str:
        """Chat using Claude API."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=CONFIG["ANTHROPIC_API_KEY"])

            self.conversation_history.append({"role": "user", "content": message})

            response = client.messages.create(
                model=CONFIG["CLAUDE_MODEL"],
                max_tokens=4096,
                system=system_prompt,
                messages=self.conversation_history[-CONFIG["MAX_HISTORY"]:]
            )

            assistant_message = response.content[0].text
            self.conversation_history.append({"role": "assistant", "content": assistant_message})

            return assistant_message
        except ImportError:
            return "Error: anthropic package not installed. Run: pip3 install anthropic"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _chat_openai(self, message: str, system_prompt: str) -> str:
        """Chat using OpenAI API."""
        try:
            import openai
            client = openai.OpenAI(api_key=CONFIG["OPENAI_API_KEY"])

            messages = [{"role": "system", "content": system_prompt}]
            self.conversation_history.append({"role": "user", "content": message})
            messages.extend(self.conversation_history[-CONFIG["MAX_HISTORY"]:])

            response = client.chat.completions.create(
                model=CONFIG["OPENAI_MODEL"],
                messages=messages,
                max_tokens=4096
            )

            assistant_message = response.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": assistant_message})

            return assistant_message
        except ImportError:
            return "Error: openai package not installed. Run: pip3 install openai"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _chat_ollama(self, message: str, system_prompt: str) -> str:
        """Chat using local Ollama."""
        try:
            url = f"{CONFIG['OLLAMA_HOST']}/api/chat"

            self.conversation_history.append({"role": "user", "content": message})

            data = json.dumps({
                "model": CONFIG["OLLAMA_MODEL"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *self.conversation_history[-CONFIG["MAX_HISTORY"]:]
                ],
                "stream": False
            }).encode()

            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode())
                assistant_message = result["message"]["content"]
                self.conversation_history.append({"role": "assistant", "content": assistant_message})
                return assistant_message
        except Exception as e:
            return f"Error (Ollama): {str(e)}\nMake sure Ollama is running: ollama serve"

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []

# ============================================================================
# COMMAND PROCESSOR
# ============================================================================

class CommandProcessor:
    """Processes commands from messages."""

    def __init__(self, mac: MacController, db: Database):
        self.mac = mac
        self.db = db
        self.commands = {
            "/screenshot": self.cmd_screenshot,
            "/apps": self.cmd_apps,
            "/open": self.cmd_open,
            "/close": self.cmd_close,
            "/files": self.cmd_files,
            "/search": self.cmd_search,
            "/system": self.cmd_system,
            "/battery": self.cmd_battery,
            "/wifi": self.cmd_wifi,
            "/volume": self.cmd_volume,
            "/brightness": self.cmd_brightness,
            "/notify": self.cmd_notify,
            "/clipboard": self.cmd_clipboard,
            "/say": self.cmd_say,
            "/reminder": self.cmd_reminder,
            "/reminders": self.cmd_reminders,
            "/notes": self.cmd_notes,
            "/note": self.cmd_note,
            "/web": self.cmd_web,
            "/download": self.cmd_download,
            "/shell": self.cmd_shell,
            "/help": self.cmd_help,
            "/clear": self.cmd_clear,
        }

    async def process(self, text: str) -> tuple[str, Optional[Path]]:
        """Process a command and return (response, optional_file_path)."""
        text = text.strip()

        # Check if it's a command
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if cmd in self.commands:
                return await self.commands[cmd](args)
            else:
                return f"Unknown command: {cmd}\nUse /help for available commands.", None

        return None, None  # Not a command

    async def cmd_screenshot(self, args: str) -> tuple[str, Optional[Path]]:
        """Take a screenshot."""
        path = self.mac.take_screenshot()
        return f"📸 Screenshot saved!", path

    async def cmd_apps(self, args: str) -> tuple[str, None]:
        """List running apps."""
        apps = self.mac.get_running_apps()
        return f"🖥️ Running Apps:\n" + "\n".join(f"• {app}" for app in apps), None

    async def cmd_open(self, args: str) -> tuple[str, None]:
        """Open an app."""
        if not args:
            return "Usage: /open <app_name>", None
        self.mac.open_app(args)
        return f"✅ Opening {args}...", None

    async def cmd_close(self, args: str) -> tuple[str, None]:
        """Close an app."""
        if not args:
            return "Usage: /close <app_name>", None
        self.mac.close_app(args)
        return f"✅ Closing {args}...", None

    async def cmd_files(self, args: str) -> tuple[str, None]:
        """List files."""
        path = args or "~"
        files = self.mac.list_files(path)
        return f"📁 Files in {path}:\n" + "\n".join(f"• {f}" for f in files[:30]), None

    async def cmd_search(self, args: str) -> tuple[str, None]:
        """Search files."""
        if not args:
            return "Usage: /search <query>", None
        files = self.mac.search_files(args)
        if files:
            return f"🔍 Search results for '{args}':\n" + "\n".join(f"• {f}" for f in files[:15]), None
        return f"No files found for '{args}'", None

    async def cmd_system(self, args: str) -> tuple[str, None]:
        """Show system info."""
        info = self.mac.get_system_info()
        lines = [f"💻 System Information:"]
        for k, v in info.items():
            lines.append(f"• {k}: {v}")
        return "\n".join(lines), None

    async def cmd_battery(self, args: str) -> tuple[str, None]:
        """Show battery status."""
        info = self.mac.get_battery_status()
        pct = info.get("percentage", "Unknown")
        charging = "⚡ Charging" if info.get("charging") else "🔋 On Battery"
        return f"🔋 Battery: {pct}% {charging}", None

    async def cmd_wifi(self, args: str) -> tuple[str, None]:
        """Show WiFi info."""
        info = self.mac.get_wifi_info()
        ssid = info.get("ssid", "Not connected")
        signal = info.get("signal", "Unknown")
        return f"📶 WiFi: {ssid} (Signal: {signal})", None

    async def cmd_volume(self, args: str) -> tuple[str, None]:
        """Set/get volume."""
        if args:
            try:
                level = int(args)
                self.mac.set_volume(level)
                return f"🔊 Volume set to {level}%", None
            except ValueError:
                return "Usage: /volume <0-100>", None
        else:
            vol = self.mac.get_volume()
            return f"🔊 Current volume: {vol}%", None

    async def cmd_brightness(self, args: str) -> tuple[str, None]:
        """Set brightness."""
        if not args:
            return "Usage: /brightness <0-100>", None
        try:
            level = int(args)
            self.mac.set_brightness(level)
            return f"☀️ Brightness set to {level}%", None
        except ValueError:
            return "Usage: /brightness <0-100>", None

    async def cmd_notify(self, args: str) -> tuple[str, None]:
        """Send notification."""
        if not args:
            return "Usage: /notify <message>", None
        self.mac.send_notification(args)
        return f"✅ Notification sent!", None

    async def cmd_clipboard(self, args: str) -> tuple[str, None]:
        """Get/set clipboard."""
        if args:
            self.mac.set_clipboard(args)
            return f"📋 Clipboard set!", None
        else:
            content = self.mac.get_clipboard()
            return f"📋 Clipboard:\n{content[:1000]}", None

    async def cmd_say(self, args: str) -> tuple[str, None]:
        """Text to speech."""
        if not args:
            return "Usage: /say <text>", None
        self.mac.say(args)
        return f"🔈 Speaking...", None

    async def cmd_reminder(self, args: str) -> tuple[str, None]:
        """Set a reminder."""
        if not args:
            return "Usage: /reminder <minutes> <message>", None
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /reminder <minutes> <message>", None
        try:
            minutes = int(parts[0])
            message = parts[1]
            remind_at = datetime.now() + timedelta(minutes=minutes)
            self.db.add_reminder(message, remind_at)
            return f"⏰ Reminder set for {minutes} minutes from now!", None
        except ValueError:
            return "Usage: /reminder <minutes> <message>", None

    async def cmd_reminders(self, args: str) -> tuple[str, None]:
        """List reminders."""
        reminders = self.db.get_pending_reminders()
        if not reminders:
            return "No pending reminders.", None
        lines = ["⏰ Pending Reminders:"]
        for r in reminders:
            lines.append(f"• {r['message']} (at {r['remind_at']})")
        return "\n".join(lines), None

    async def cmd_notes(self, args: str) -> tuple[str, None]:
        """List notes."""
        notes = self.db.get_notes()
        if not notes:
            return "No notes yet. Use /note <title> <content> to create one.", None
        lines = ["📝 Your Notes:"]
        for n in notes:
            lines.append(f"• [{n['id']}] {n['title']}")
        return "\n".join(lines), None

    async def cmd_note(self, args: str) -> tuple[str, None]:
        """Create a note."""
        if not args:
            return "Usage: /note <title> <content>", None
        parts = args.split(maxsplit=1)
        title = parts[0]
        content = parts[1] if len(parts) > 1 else ""
        note_id = self.db.add_note(title, content)
        return f"📝 Note saved (ID: {note_id})!", None

    async def cmd_web(self, args: str) -> tuple[str, None]:
        """Web search."""
        if not args:
            return "Usage: /web <search query>", None
        query = urllib.parse.quote(args)
        url = f"https://www.google.com/search?q={query}"
        self.mac.run_shell(f"open '{url}'")
        return f"🌐 Opening search for: {args}", None

    async def cmd_download(self, args: str) -> tuple[str, None]:
        """Download a file."""
        if not args:
            return "Usage: /download <url>", None
        downloads = Path.home() / "Downloads"
        filename = args.split("/")[-1].split("?")[0] or "download"
        filepath = downloads / filename
        result = self.mac.run_shell(f"curl -L -o '{filepath}' '{args}'")
        return f"⬇️ Downloaded to: {filepath}", None

    async def cmd_shell(self, args: str) -> tuple[str, None]:
        """Execute shell command."""
        if not args:
            return "Usage: /shell <command>", None
        result = self.mac.run_shell(args)
        self.db.log_command(args, result)
        return f"💻 Output:\n```\n{result}\n```", None

    async def cmd_help(self, args: str) -> tuple[str, None]:
        """Show help."""
        help_text = """
🤖 **Personal AI Assistant Commands**

**System:**
• /screenshot - Take a screenshot
• /system - Show system info
• /battery - Battery status
• /wifi - WiFi info
• /volume [0-100] - Get/set volume
• /brightness <0-100> - Set brightness

**Apps:**
• /apps - List running apps
• /open <app> - Open an app
• /close <app> - Close an app

**Files:**
• /files [path] - List files
• /search <query> - Search files
• /download <url> - Download file

**Utilities:**
• /notify <msg> - Send notification
• /clipboard [text] - Get/set clipboard
• /say <text> - Text to speech
• /shell <cmd> - Run shell command
• /web <query> - Web search

**Notes & Reminders:**
• /notes - List notes
• /note <title> <content> - Save note
• /reminder <mins> <msg> - Set reminder
• /reminders - List reminders

**Chat:**
• /clear - Clear chat history
• /help - Show this help

Or just chat with me naturally! 💬
"""
        return help_text, None

    async def cmd_clear(self, args: str) -> tuple[str, None]:
        """Clear chat history."""
        self.db.clear_history()
        return "🗑️ Chat history cleared!", None

# ============================================================================
# TELEGRAM BOT
# ============================================================================

class TelegramBot:
    """Telegram bot for the AI assistant."""

    def __init__(self):
        self.mac = MacController()
        self.db = Database(CONFIG["DATA_DIR"] / "assistant.db")
        self.ai = AIEngine(CONFIG["AI_PROVIDER"])
        self.commands = CommandProcessor(self.mac, self.db)
        self.owner_id = CONFIG["TELEGRAM_OWNER_ID"]

    def is_owner(self, user_id: int) -> bool:
        """Check if user is the owner."""
        return user_id == self.owner_id

    def get_system_prompt(self) -> str:
        """Generate the system prompt with current context."""
        return SYSTEM_PROMPT.format(
            name=CONFIG["ASSISTANT_NAME"],
            owner="YS",
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            os_version=platform.mac_ver()[0]
        )

    async def handle_message(self, user_id: int, text: str) -> tuple[str, Optional[Path]]:
        """Handle an incoming message."""
        # Security check
        if not self.is_owner(user_id):
            return "⛔ Sorry, I only respond to my owner.", None

        # Check for commands first
        cmd_response, file_path = await self.commands.process(text)
        if cmd_response:
            return cmd_response, file_path

        # Otherwise, chat with AI
        self.db.add_message("user", text)
        response = await self.ai.chat(text, self.get_system_prompt())
        self.db.add_message("assistant", response)

        # Check if AI response contains commands to execute
        file_path = None
        if "/screenshot" in response.lower():
            _, file_path = await self.commands.cmd_screenshot("")

        return response, file_path

    async def check_reminders(self) -> List[str]:
        """Check and return due reminders."""
        reminders = self.db.get_pending_reminders()
        messages = []
        for r in reminders:
            messages.append(f"⏰ Reminder: {r['message']}")
            self.db.complete_reminder(r['id'])
            self.mac.send_notification(r['message'], "Reminder")
        return messages

    def run(self):
        """Run the Telegram bot."""
        try:
            from telegram import Update
            from telegram.ext import Application, CommandHandler, MessageHandler, filters
        except ImportError:
            print("Error: python-telegram-bot not installed.")
            print("Run: pip3 install python-telegram-bot")
            return

        if CONFIG["TELEGRAM_BOT_TOKEN"] == "YOUR_BOT_TOKEN_HERE":
            print("\n" + "="*60)
            print("SETUP REQUIRED")
            print("="*60)
            print("\n1. Get a Telegram Bot Token:")
            print("   - Open Telegram and search for @BotFather")
            print("   - Send /newbot and follow instructions")
            print("   - Copy the token")
            print("\n2. Get your Telegram User ID:")
            print("   - Search for @userinfobot on Telegram")
            print("   - It will tell you your user ID")
            print("\n3. Set environment variables:")
            print("   export TELEGRAM_BOT_TOKEN='your_token_here'")
            print("   export TELEGRAM_OWNER_ID='your_user_id'")
            print("   export ANTHROPIC_API_KEY='your_claude_api_key'")
            print("\n4. Or edit the CONFIG section in this file")
            print("="*60 + "\n")
            return

        if self.owner_id == 0:
            print("Error: TELEGRAM_OWNER_ID not set!")
            print("Get your ID from @userinfobot on Telegram")
            return

        app = Application.builder().token(CONFIG["TELEGRAM_BOT_TOKEN"]).build()

        async def start(update: Update, context):
            if not self.is_owner(update.effective_user.id):
                await update.message.reply_text("⛔ Unauthorized")
                return
            await update.message.reply_text(
                f"👋 Hello! I'm {CONFIG['ASSISTANT_NAME']}, your personal AI assistant.\n\n"
                "I can help you control your Mac, answer questions, and more!\n\n"
                "Type /help to see what I can do."
            )

        async def handle_text(update: Update, context):
            user_id = update.effective_user.id
            text = update.message.text

            response, file_path = await self.handle_message(user_id, text)

            # Send file if there is one
            if file_path and file_path.exists():
                await update.message.reply_photo(photo=open(file_path, 'rb'))

            # Send text response (split if too long)
            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
            else:
                await update.message.reply_text(response)

        async def reminder_checker(context):
            """Background task to check reminders."""
            messages = await self.check_reminders()
            for msg in messages:
                await context.bot.send_message(chat_id=self.owner_id, text=msg)

        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(MessageHandler(filters.COMMAND, handle_text))

        # Schedule reminder checker (optional - requires job-queue extra)
        if app.job_queue:
            app.job_queue.run_repeating(reminder_checker, interval=60, first=10)
            print("✅ Reminder system enabled")
        else:
            print("⚠️  Reminders disabled (install: pip3 install 'python-telegram-bot[job-queue]')")

        print(f"\n🤖 {CONFIG['ASSISTANT_NAME']} is running!")
        print(f"📱 Open Telegram and message your bot")
        print(f"🔒 Only responding to user ID: {self.owner_id}")
        print("\nPress Ctrl+C to stop\n")

        # Use run_polling directly (it manages its own event loop)
        app.run_polling(drop_pending_updates=True)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Personal AI Assistant for macOS")
    parser.add_argument("--test", action="store_true", help="Run in test mode (no Telegram)")
    parser.add_argument("--setup", action="store_true", help="Show setup instructions")
    args = parser.parse_args()

    if args.setup:
        print("""
╔══════════════════════════════════════════════════════════════╗
║           Personal AI Assistant - Setup Guide                ║
╚══════════════════════════════════════════════════════════════╝

STEP 1: Install Dependencies
────────────────────────────
pip3 install python-telegram-bot anthropic

STEP 2: Create Telegram Bot
───────────────────────────
1. Open Telegram and search for @BotFather
2. Send /newbot
3. Choose a name (e.g., "My Personal Assistant")
4. Choose a username (e.g., "my_personal_ai_bot")
5. Copy the API token you receive

STEP 3: Get Your Telegram User ID
─────────────────────────────────
1. Search for @userinfobot on Telegram
2. Start a chat with it
3. It will reply with your user ID (a number)

STEP 4: Get Claude API Key
──────────────────────────
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Go to API Keys section
4. Create a new key and copy it

STEP 5: Set Environment Variables
─────────────────────────────────
Add these to your ~/.zshrc or ~/.bash_profile:

export TELEGRAM_BOT_TOKEN='your_bot_token_here'
export TELEGRAM_OWNER_ID='your_user_id_here'
export ANTHROPIC_API_KEY='your_claude_api_key'

Then run: source ~/.zshrc

STEP 6: Run the Assistant
─────────────────────────
python3 personal_ai_assistant.py

ALTERNATIVE: Use Ollama (Free, Local AI)
────────────────────────────────────────
1. Install Ollama: brew install ollama
2. Run: ollama pull llama3
3. Run: ollama serve
4. Set: export AI_PROVIDER='ollama'

Then you don't need the ANTHROPIC_API_KEY!

""")
        return

    if args.test:
        # Test mode - run without Telegram
        print("Running in test mode...")
        mac = MacController()
        db = Database(CONFIG["DATA_DIR"] / "assistant.db")
        ai = AIEngine(CONFIG["AI_PROVIDER"])
        commands = CommandProcessor(mac, db)

        print(f"\n🤖 {CONFIG['ASSISTANT_NAME']} Test Mode")
        print("Type commands or chat. Type 'exit' to quit.\n")

        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() == 'exit':
                    break

                # Process command or chat
                response, file_path = asyncio.run(commands.process(user_input))
                if response:
                    print(f"\n{CONFIG['ASSISTANT_NAME']}: {response}\n")
                else:
                    response = asyncio.run(ai.chat(user_input, SYSTEM_PROMPT.format(
                        name=CONFIG['ASSISTANT_NAME'],
                        owner="YS",
                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        os_version=platform.mac_ver()[0]
                    )))
                    print(f"\n{CONFIG['ASSISTANT_NAME']}: {response}\n")
            except KeyboardInterrupt:
                break

        print("\nGoodbye!")
        return

    # Run Telegram bot
    bot = TelegramBot()
    bot.run()

if __name__ == "__main__":
    main()
