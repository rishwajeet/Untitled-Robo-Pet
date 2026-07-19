"""Bounded Mac control for Bittu — a WHITELIST of safe verbs, never raw shell.

Deliberately NOT a general command runner: this is voice-driven in a loud
room where strangers talk to the robot, so one misheard "delete everything"
must be impossible. Only the verbs below exist. Adding raw shell here would
be a security hole, not a feature.
"""
import shutil
import subprocess

import journal

_MAC = shutil.which("osascript") is not None

# app name -> how to open. Keep to well-known, harmless apps.
APPS = {
    "youtube": ("url", "https://youtube.com"),
    "google": ("url", "https://google.com"),
    "spotify": ("app", "Spotify"),
    "safari": ("app", "Safari"),
    "chrome": ("app", "Google Chrome"),
    "notes": ("app", "Notes"),
    "calculator": ("app", "Calculator"),
    "finder": ("app", "Finder"),
    "terminal": ("app", "Terminal"),
    "vscode": ("app", "Visual Studio Code"),
    "code": ("app", "Visual Studio Code"),
    "music": ("app", "Music"),
}


def _osa(script: str) -> str:
    if not _MAC:
        return "PC control only works on the Mac host"
    try:
        subprocess.run(["osascript", "-e", script], check=True,
                       capture_output=True, timeout=6)
        return "done"
    except Exception as e:
        return f"failed: {e}"


def open_app(name: str) -> str:
    key = (name or "").strip().lower()
    for app_key, (kind, target) in APPS.items():
        if app_key in key:
            journal.log("pc", f"open {app_key}")
            if kind == "url":
                return _osa(f'open location "{target}"')
            return _osa(f'tell application "{target}" to activate')
    return (f"I can open: {', '.join(sorted(APPS))}. "
            f"'{name}' isn't on my safe list.")


def media(action: str) -> str:
    a = (action or "").strip().lower()
    # System-wide media keys via key codes (play/pause=16 via 'playpause' script)
    if "pause" in a or "play" in a or "stop" in a:
        journal.log("pc", "media play/pause")
        return _osa('tell application "System Events" to key code 16')  # F8/play
    if "next" in a or "skip" in a:
        return _osa('tell application "System Events" to key code 17')
    if "prev" in a or "back" in a:
        return _osa('tell application "System Events" to key code 18')
    return "I can play/pause, next, or previous."


def volume(direction: str) -> str:
    d = (direction or "").strip().lower()
    if "up" in d or "louder" in d or "increase" in d:
        journal.log("pc", "volume up")
        return _osa("set volume output volume (output volume of (get volume settings) + 15)")
    if "down" in d or "lower" in d or "quiet" in d or "decrease" in d:
        journal.log("pc", "volume down")
        return _osa("set volume output volume (output volume of (get volume settings) - 15)")
    if "mute" in d:
        return _osa("set volume with output muted")
    if "unmute" in d or "max" in d:
        return _osa("set volume output volume 70")
    return "I can turn volume up, down, mute, or unmute."



def web_search(query: str) -> str:
    """Open a web search — the search-and-open the whitelist was missing."""
    import urllib.parse
    q = urllib.parse.quote((query or "").strip())
    if not q:
        return "search for what?"
    journal.log("pc", f"search {query[:60]}")
    return _osa(f'open location "https://www.google.com/search?q={q}"')


def youtube_search(query: str) -> str:
    import urllib.parse
    q = urllib.parse.quote((query or "").strip())
    journal.log("pc", f"youtube {query[:60]}")
    return _osa(f'open location "https://www.youtube.com/results?search_query={q}"')


def see_screen(_: str = "") -> str:
    """Screenshot the Mac and read it with vision — he SEES the screen,
    not just the camera. Safe: pure perception, no actuation."""
    import base64
    import tempfile
    from openai import OpenAI
    path = tempfile.mktemp(suffix=".png")
    try:
        subprocess.run(["screencapture", "-x", "-t", "png", path],
                       check=True, timeout=6)
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        journal.log("pc", "screenshot -> vision")
        r = OpenAI().chat.completions.create(
            model="gpt-4o-mini", max_tokens=120,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "This is the human's computer screen. "
                 "Describe what's on it / what they're doing, briefly."},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{b64}", "detail": "low"}}]}])
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"couldn't see the screen: {e}"


def type_text(text: str) -> str:
    """Type text into the frontmost app. Real actuation — on the human's own
    machine. (For anything destructive, gate behind the physical button.)"""
    if not text:
        return "type what?"
    journal.log("pc", f"type: {text[:40]}")
    if shutil.which("cliclick"):
        try:
            subprocess.run(["cliclick", f"t:{text}"], check=True, timeout=6)
            return "typed"
        except Exception as e:
            return f"type failed: {e}"
    safe = text.replace('"', "'")
    return _osa(f'tell application "System Events" to keystroke "{safe}"')


# tool defs for the openai loop
def openai_tools() -> list:
    def t(name, desc, param=None):
        props = {param: {"type": "string"}} if param else {}
        return {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props,
                           "required": [param] if param else []}}}
    return [
        t("open_app", "Open a bare app/site (no search). ONLY when they just "
          "want the app itself. If they mention searching/playing/finding "
          "something, use web_search or youtube_search instead. Safe list: "
          + ", ".join(sorted(APPS)) + ".", "name"),
        t("media", "Control media playback on the Mac: play, pause, next, previous.", "action"),
        t("volume", "Change the Mac's volume: up, down, mute, unmute.", "direction"),
        t("web_search", "Open Google results for a query. Use whenever someone "
          "wants to look something up, find info, or search the web.", "query"),
        t("youtube_search", "Open YouTube search results for a query. USE THIS "
          "(not open_app) whenever someone wants to PLAY, WATCH, or FIND any "
          "video/song/music/channel — e.g. 'play a comedy video', 'watch lofi', "
          "'find CGP Grey'. Pass the topic as the query.", "query"),
        t("see_screen", "Look at / read what is currently on the human's computer screen."),
        t("type_text", "Type text into whatever app is focused on the Mac.", "text"),
    ]


DISPATCH = {"open_app": open_app, "media": media, "volume": volume,
            "web_search": web_search, "youtube_search": youtube_search,
            "see_screen": see_screen, "type_text": type_text}


def call(name: str, arguments: dict) -> str:
    fn = DISPATCH.get(name)
    if not fn:
        return f"unknown pc action {name}"
    args = list(arguments.values())
    return fn(args[0] if args else "")
