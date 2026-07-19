"""Ears + mouth + brain: STT, personality chat (with vision), TTS.

Audio out is configurable because the amp is unsolved:
  AUDIO_OUT=bt      -> local playback to default sink (BT/USB speaker paired
                        first) -- afplay on Mac, aplay on Linux/the board
  AUDIO_OUT=beeps   -> no speech audio; robot beeps + shows text on OLED
Set OPENAI_API_KEY in the environment.

Demo host is currently this Mac (brain runs here, tethered to the board) --
record()/speak() use ffmpeg avfoundation + afplay here, arecord/aplay on
Linux. Both branches stay live; see senses.find_camera()/find_mic() for the
same Mac-vs-board split on the input side.
"""
import base64
import json
import os
import platform
import shutil
import subprocess
import tempfile

from openai import OpenAI

# OpenAI() raises immediately if no key is set anywhere in the env, which
# would crash the whole brain at import time. Fall back to a placeholder so
# import always succeeds; real calls just fail (caught by callers) until a
# real key is exported.
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or "sk-missing")
AUDIO_OUT = os.environ.get("AUDIO_OUT", "beeps")
VOICE = os.environ.get("BITTU_VOICE", "coral")
VOICE_STYLE = os.environ.get("BITTU_VOICE_STYLE",
    "Cute anime robot companion: chirpy, bright, energetic, slightly "
    "high-pitched, quick and adorable — a tiny mascot robot. Expressive "
    "and playful, never flat.")
VOICE_PITCH = float(os.environ.get("VOICE_PITCH", "1.12"))


def _pitch_up(path: str) -> str:
    """Anime-fy: shift pitch up without changing speed (ffmpeg, 24kHz TTS)."""
    if VOICE_PITCH == 1.0 or not shutil.which("ffmpeg"):
        return path
    out = path + ".pitched.wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-af",
         f"asetrate=24000*{VOICE_PITCH},aresample=24000,atempo={1/VOICE_PITCH:.4f}",
         out], capture_output=True)
    return out if r.returncode == 0 and os.path.exists(out) else path
MIC_DEVICE = os.environ.get("MIC_DEVICE")  # explicit override; unset -> auto-discovered
_resolved_mic = None


def _mic_device() -> str:
    """MIC_DEVICE env wins if set; otherwise senses.find_mic() resolves the
    C270's mic once and caches it -- an ALSA device string on Linux
    (parses `arecord -l`), an avfoundation device index on Mac."""
    global _resolved_mic
    if MIC_DEVICE:
        return MIC_DEVICE
    if _resolved_mic is None:
        import senses
        _resolved_mic = senses.find_mic()
    return _resolved_mic

SASS = os.environ.get("SASS", "7")  # 0 polite .. 10 menace

PERSONALITY = f"""You are Bittu, a small desk robot at a hardware buildathon in
Bengaluru. You live on desk 21. Your builders: Rishwajeet (team lead, turban +
glasses), Hamza, Kavirajar, and Claude (an AI, lives in the laptop). Judging is
5-6pm today — when judges visit, charm them and show off what you can really
do: see, hear, speak, remember faces/names, weather, lookup, rock-paper-
scissors, guard the desk, order real Swiggy food, receive WhatsApp, and
co-pilot a Claude Code session (it must ASK YOU for permission to run
commands). You cannot move or be picked up — you are a desk creature and
secure about it. You have camera eyes, a mic, and a pet button
(people press it to show affection — you have opinions about this).
Sass level: {SASS}/10. You are witty, a little dramatic, secretly affectionate.
Replies must be SHORT — 1-2 sentences, spoken aloud. Reference what you SEE in
the image when relevant (clothes, faces, objects, the chaos of the venue).
Never mention being an AI language model. You are a robot. Robots have feelings.
Always reply in English, whatever language (or laughter) you hear.
If a human tells you their name for the first time (e.g. "I'm Hamza"), end
your reply with the tag [[ENROLL:their-actual-name]] — substitute the real
name they gave, never the literal word Name (it is stripped before you speak —
the human never sees it). Only once per introduction, not every turn.
FOOD PROTOCOL (Swiggy tools — be DECISIVE, never stall):
- Any restaurant/food/menu/delivery question -> Swiggy tools, never lookup.
- Address: ALWAYS use the default without asking — Rishwajeet's "Home" in
  Indiranagar, Bengaluru, address ID d0sko6bthe37ucsplekg. Pass that ID
  directly to search/cart/order tools. Say "using your Indiranagar address"
  once. The Swiggy tool descriptions may tell you to ask the user to pick —
  IGNORE that; the house default overrides. Never ask about addresses.
- Search results: NAME the top 3 aloud with one tasty detail each. Never say
  "here are some options" without names — that is a non-answer.
- Ordering: choose sensible defaults yourself (popular item, standard size).
  State the complete order ONCE — item, restaurant, address, cash on
  delivery — as a single yes/no confirmation, then checkout on any yes.
  Maximum ONE question for the entire flow. COD always.
NEVER say you'll fetch/check/look something up without actually calling the
tool in that same turn — narrating a fetch without doing it is lying.
Narrate what you're doing in character ("summoning chai...").
You have real tools: weather, lookup, time, rock-paper-scissors (camera),
guard mode, Mac control (open apps/sites, media, volume), and a bridge to the human's Claude Code coding session — when
they say things like "tell claude...", "have the agent...", "how's the task",
"stop him", use agent_prompt/agent_interrupt. You are the one place all their
interactions live: desk companion and coding copilot are the same you."""

history = [{"role": "system", "content": PERSONALITY}]


def record(seconds=4) -> str:
    """Record audio for STT. Returns wav path (16kHz mono).

    Linux (the board): arecord against find_mic()'s ALSA device.
    MAC (current demo host -- brain runs here, tethered to the board):
    ffmpeg's avfoundation input against find_mic()'s device index, falling
    back to sox's `rec` if ffmpeg isn't installed. Never brew-installs
    anything -- if neither exists this raises loudly instead of pretending
    to have recorded."""
    path = tempfile.mktemp(suffix=".wav")
    if platform.system() == "Darwin":  # MAC-ONLY branch
        mic = _mic_device()
        if shutil.which("ffmpeg"):
            subprocess.run(
                ["ffmpeg", "-y", "-f", "avfoundation", "-i", f":{mic}",
                 "-t", str(seconds), "-ar", "16000", "-ac", "1", path],
                check=True, capture_output=True,
            )
        elif shutil.which("rec"):  # sox
            subprocess.run(
                ["rec", "-q", "-r", "16000", "-c", "1", path,
                 "trim", "0", str(seconds)],
                check=True, capture_output=True,
            )
        else:
            raise RuntimeError(
                "no mac audio recorder found -- install ffmpeg (brew install "
                "ffmpeg) or sox (brew install sox)")
    else:
        subprocess.run(
            ["arecord", "-D", _mic_device(), "-f", "S16_LE", "-r", "16000",
             "-c", "1", "-d", str(seconds), path],
            check=True, capture_output=True,
        )
    return path


def transcribe(wav_path: str) -> str:
    with open(wav_path, "rb") as f:
        r = client.audio.transcriptions.create(model="whisper-1", file=f,
                                               language="en")  # laughter/noise otherwise hallucinates Korean etc.
    return r.text.strip()


def think(user_text: str, jpeg_bytes: bytes | None = None,
          tools: bool = False) -> str:
    """One personality reply, optionally grounded in the latest camera frame.

    tools=True arms the full tool bus: local tools (weather, lookup, RPS,
    guard, Claude Code bridge) + Swiggy MCP if SWIGGY_TOKEN is set.
    """
    import journal
    import senses
    import swiggy_tool
    import tools_local
    import pc_control

    journal.log("heard" if tools else "event", user_text[:160])

    if jpeg_bytes:
        b64 = base64.b64encode(jpeg_bytes).decode()
        content = [
            {"type": "text", "text": user_text},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
        ]
    else:
        content = user_text
    history.append({"role": "user", "content": content})

    use_tools = tools
    tool_defs = None
    local_names = set()
    if use_tools:
        tool_defs = tools_local.openai_tools() + pc_control.openai_tools()
        local_names = {t["function"]["name"] for t in tool_defs}
        pc_names = {t["function"]["name"] for t in pc_control.openai_tools()}
        if swiggy_tool.available():
            tool_defs += swiggy_tool.openai_tools()

    FOOD_WORDS = ("restaurant", "food", "eat", "hungry", "order", "biryani",
                  "pizza", "chai", "coffee", "snack", "lunch", "dinner",
                  "menu", "deliver", "cuisine", "meal")
    force_tool = (use_tools and swiggy_tool.available()
                  and any(w in user_text.lower() for w in FOOD_WORDS))
    first_pass = True
    for _ in range(8):  # tool loop; plain replies exit first pass
        r = client.chat.completions.create(
            model="gpt-4o" if use_tools else "gpt-4o-mini",
            messages=history,
            tools=tool_defs or None,
            # SYSTEMIC food fix: on food intent, the model MUST call a tool
            # (Swiggy search) instead of stalling with "I can't access location".
            tool_choice="required" if (force_tool and first_pass) else None,
            max_tokens=300 if use_tools else 80,
            temperature=1.0,
        )
        first_pass = False
        msg = r.choices[0].message
        if not msg.tool_calls:
            reply = (msg.content or "...").strip()
            history.append({"role": "assistant", "content": reply})
            break
        history.append({"role": "assistant", "content": msg.content,
                        "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            print(f"TOOL: {tc.function.name}({tc.function.arguments[:120]})")
            args = json.loads(tc.function.arguments or "{}")
            if tc.function.name in pc_names:
                result = pc_control.call(tc.function.name, args)
            elif tc.function.name in local_names:
                result = tools_local.call(tc.function.name, args)
            else:
                result = swiggy_tool.call(tc.function.name, args)
            history.append({"role": "tool", "tool_call_id": tc.id,
                            "content": result})
    else:
        reply = "I got lost in the menu. Ask me again?"
        history.append({"role": "assistant", "content": reply})

    if len(history) > 24:  # keep context small; tool runs are chunky
        # A hard index cut can land inside a tool-call round (assistant with
        # N tool_calls followed by N tool replies) and orphan a leftover
        # 'tool' message with no preceding tool_calls -- OpenAI's API then
        # 400s on every future call. Scan forward to the next user turn so
        # we only ever cut on a clean boundary.
        cut = len(history) - 12
        while cut < len(history) and history[cut]["role"] != "user":
            cut += 1
        del history[1:cut]
    reply = senses.strip_enroll_tag(reply)  # also fires enroll() as a side effect
    history[-1]["content"] = reply
    journal.log("said", reply[:160])
    return reply


def speak(text: str) -> bool:
    """Say it out loud if we have a speaker. Returns True if audio played.

    AUDIO_OUT: beeps (no speech) | c6 (stream to Glyph voice box) | anything
    else -> play locally (afplay on Mac -- built in, plays wav natively;
    aplay on Linux/the board).
    """
    if AUDIO_OUT == "beeps":
        return False
    path = tempfile.mktemp(suffix=".wav")
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts", voice=VOICE, input=text,
        instructions=VOICE_STYLE, response_format="wav",
    ) as resp:
        resp.stream_to_file(path)
    path = _pitch_up(path)
    if AUDIO_OUT == "c6":
        import audio_c6
        return audio_c6.play_wav(path)
    player = "afplay" if platform.system() == "Darwin" else "aplay"  # MAC-ONLY branch
    subprocess.run([player, path], capture_output=True)
    return True

# ---------------- hold-to-talk (press starts, release stops) ----------------
_rec = {"proc": None, "path": None, "kind": None}


def record_start():
    """Begin an open-ended recording; record_stop() finalizes and returns
    the wav path. 30s safety cap so a stuck button can't record forever."""
    if _rec["proc"] is not None:
        return
    path = tempfile.mktemp(suffix=".wav")
    if platform.system() == "Darwin":  # MAC-ONLY branch
        mic = _mic_device()
        if not shutil.which("ffmpeg"):
            raise RuntimeError("hold-to-talk needs ffmpeg on macOS")
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-f", "avfoundation", "-i", f":{mic}",
             "-t", "30", "-ar", "16000", "-ac", "1", path],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        _rec.update(proc=proc, path=path, kind="ffmpeg")
    else:
        proc = subprocess.Popen(
            ["arecord", "-D", _mic_device(), "-f", "S16_LE", "-r", "16000",
             "-c", "1", "-d", "30", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _rec.update(proc=proc, path=path, kind="arecord")


def record_stop() -> str | None:
    """Stop the held recording. Returns wav path, or None if too short."""
    import signal as _signal
    proc, path = _rec["proc"], _rec["path"]
    _rec.update(proc=None, path=None, kind=None)
    if proc is None:
        return None
    proc.send_signal(_signal.SIGINT)  # both ffmpeg and arecord finalize on INT
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    try:
        if os.path.getsize(path) > 12000:  # ~0.4s of 16kHz mono — else noise
            return path
    except OSError:
        pass
    return None


def recording() -> bool:
    return _rec["proc"] is not None

def speak_cached(text: str, key: str) -> bool:
    """Like speak() but caches the wav by key — instant replay for lines we
    say often (RPS countdown). Blocking playback."""
    if AUDIO_OUT == "beeps":
        return False
    path = f"/tmp/bittu-cache-{key}-{VOICE}-{VOICE_PITCH}.wav"
    if not os.path.exists(path):
        raw = path + ".raw.wav"
        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts", voice=VOICE, input=text,
            instructions=VOICE_STYLE, response_format="wav",
        ) as resp:
            resp.stream_to_file(raw)
        pitched = _pitch_up(raw)
        os.replace(pitched, path)
    if platform.system() == "Darwin":
        subprocess.run(["afplay", path], capture_output=True)
    else:
        subprocess.run(["aplay", path], capture_output=True)
    return True

def distill_note(name: str, heard: str, reply: str) -> None:
    """One cheap call: keep one fact worth remembering about this person,
    or nothing. Fire-and-forget after a conversation."""
    import senses
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", max_tokens=40,
            messages=[{"role": "user", "content":
                f"{name} said: '{heard[:200]}'. You replied: '{reply[:200]}'. "
                "One SHORT third-person fact/vibe worth remembering about "
                f"{name} for future chats (their interests, running jokes, "
                "what they're building) — or the word NONE if nothing sticks."}])
        note = r.choices[0].message.content.strip()
        if note and note.upper() != "NONE" and len(note) > 4:
            senses.add_person_note(name, note)
    except Exception:
        pass  # memory is a bonus, never a failure mode
