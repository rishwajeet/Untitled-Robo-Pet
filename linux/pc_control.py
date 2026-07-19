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


# tool defs for the openai loop
def openai_tools() -> list:
    def t(name, desc, param):
        return {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object",
                           "properties": {param: {"type": "string"}},
                           "required": [param]}}}
    return [
        t("open_app", "Open an app or site on the human's Mac. Safe list only: "
          + ", ".join(sorted(APPS)) + ".", "name"),
        t("media", "Control media playback on the Mac: play, pause, next, previous.", "action"),
        t("volume", "Change the Mac's volume: up, down, mute, unmute.", "direction"),
    ]


DISPATCH = {"open_app": open_app, "media": media, "volume": volume}


def call(name: str, arguments: dict) -> str:
    fn = DISPATCH.get(name)
    if not fn:
        return f"unknown pc action {name}"
    args = list(arguments.values())
    return fn(args[0] if args else "")
