"""Bittu's local superpowers: weather, knowledge, time, RPS, guard mode,
and the two-way bridge into a live Claude Code session on the laptop.

All exposed as OpenAI function-calling tools; swiggy_tool.py adds food.
Same pattern for every future MCP/tool — this file is the tool bus.
"""
import base64
import json
import os
import random
import subprocess
import time

import requests

import journal

BRIDGE = os.environ.get("BRIDGE_URL", "")  # e.g. http://<laptop-ip>:8400

GUARD = {"on": False}
_frame_source = None  # set by brain.py: callable -> jpeg bytes


def set_frame_source(fn):
    global _frame_source
    _frame_source = fn


# ---------------- tool implementations ----------------

def weather(city: str) -> str:
    try:
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1}, timeout=6).json()
        loc = g["results"][0]
        w = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": loc["latitude"], "longitude": loc["longitude"],
            "current": "temperature_2m,precipitation,weather_code"},
            timeout=6).json()["current"]
        return (f"{loc['name']}: {w['temperature_2m']}°C, "
                f"precipitation {w['precipitation']}mm")
    except Exception as e:
        return f"weather lookup failed: {e}"


def lookup(topic: str) -> str:
    try:
        r = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + requests.utils.quote(topic), timeout=6).json()
        return r.get("extract", "no summary found")[:600]
    except Exception as e:
        return f"lookup failed: {e}"


def current_time(_: str = "") -> str:
    return time.strftime("%A %H:%M")


def play_rps(_: str = "") -> str:
    """Rock-paper-scissors against the camera. Grabs a frame, reads the
    human's hand via vision, robot picks randomly. Returns the verdict."""
    if not _frame_source:
        return "no camera available"
    from openai import OpenAI
    import voice
    # the game clock: he counts down himself; hand shows on SHOOT
    voice.speak_cached("Rock... paper... scissors... SHOOT! Show me your hand!",
                       "rps-countdown")
    time.sleep(1.2)  # hand lands after SHOOT
    jpeg = _frame_source()
    if not jpeg:
        return "camera gave me nothing"
    robot = random.choice(["rock", "paper", "scissors"])
    b64 = base64.b64encode(jpeg).decode()
    # same missing-key guard as voice.py's client -- OpenAI() alone raises
    # at construction time if OPENAI_API_KEY is unset.
    r = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or "sk-missing").chat.completions.create(
        model="gpt-4o-mini", max_tokens=10,
        messages=[{"role": "user", "content": [
            {"type": "text", "text":
             "A hand gesture for rock-paper-scissors. Reply with exactly one "
             "word: rock, paper, scissors, or none."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                           "detail": "low"}}]}])
    human = r.choices[0].message.content.strip().lower()
    if "none" in human:
        return "I couldn't see a hand. Hold it up to my eye and go again."
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    if human == robot:
        verdict = "draw"
    elif beats.get(robot) == human:
        verdict = "I WIN"
    else:
        verdict = "human wins (this round)"
    return f"human threw {human}, I threw {robot}: {verdict}"


def set_guard(on: str) -> str:
    GUARD["on"] = str(on).lower() in ("true", "on", "yes", "1")
    journal.log("guard", f"guard mode {'ON' if GUARD['on'] else 'off'}")
    return f"guard mode {'engaged. Nobody touches this desk.' if GUARD['on'] else 'off. At ease.'}"


def agent_prompt(text: str) -> str:
    """Send a prompt into the live Claude Code session on the laptop."""
    if not BRIDGE:
        return "no laptop bridge configured (set BRIDGE_URL)"
    try:
        requests.post(f"{BRIDGE}/prompt", json={"text": text}, timeout=4)
        return f"sent to the coding agent: '{text}'. It'll report back through me."
    except Exception as e:
        return f"bridge unreachable: {e}"


def agent_interrupt(_: str = "") -> str:
    if not BRIDGE:
        return "no laptop bridge configured"
    try:
        requests.post(f"{BRIDGE}/interrupt", json={}, timeout=4)
        return "interrupted the coding agent. It has been silenced."
    except Exception as e:
        return f"bridge unreachable: {e}"


# ---------------- OpenAI wiring ----------------

def _tool(name, desc, param=None):
    props = {param: {"type": "string"}} if param else {}
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": [param] if param else []}}}


def openai_tools() -> list:
    return [
        _tool("weather", "Current weather for a city.", "city"),
        _tool("lookup", "Short factual summary of a topic (Wikipedia).", "topic"),
        _tool("current_time", "Current day and time."),
        _tool("play_rps", "Play one round of rock-paper-scissors. Call this "
              "IMMEDIATELY whenever someone wants to play, says yes to a "
              "rematch, or says anything like 'let's go/again/one more' in a "
              "game context. The tool runs its own spoken countdown and "
              "captures on SHOOT. NEVER announce a round without calling "
              "this — talking about playing without calling it is refusing "
              "to play."),
        _tool("set_guard", "Turn desk guard mode on/off. When on, motion at "
              "the desk triggers an alert and a photo.", "on"),
        _tool("agent_prompt", "Send a task/instruction/reply to the live "
              "Claude Code coding session on the laptop.", "text"),
        _tool("agent_interrupt", "Stop/interrupt the coding agent right now."),
    ]


DISPATCH = {"weather": weather, "lookup": lookup, "current_time": current_time,
            "play_rps": play_rps, "set_guard": set_guard,
            "agent_prompt": agent_prompt, "agent_interrupt": agent_interrupt}


def call(name: str, arguments: dict) -> str:
    fn = DISPATCH.get(name)
    if not fn:
        return f"unknown tool {name}"
    args = list(arguments.values())
    result = fn(args[0] if args else "")
    journal.log("tool", f"{name}({json.dumps(arguments)}) -> {result[:80]}")
    return result
