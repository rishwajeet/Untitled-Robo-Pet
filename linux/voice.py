"""Ears + mouth + brain: STT, personality chat (with vision), TTS.

Audio out is configurable because the amp is unsolved:
  AUDIO_OUT=bt      -> aplay to default sink (BT/USB speaker paired first)
  AUDIO_OUT=beeps   -> no speech audio; robot beeps + shows text on OLED
Set OPENAI_API_KEY in the environment.
"""
import base64
import json
import os
import subprocess
import tempfile

from openai import OpenAI

# OpenAI() raises immediately if no key is set anywhere in the env, which
# would crash the whole brain at import time. Fall back to a placeholder so
# import always succeeds; real calls just fail (caught by callers) until a
# real key is exported.
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or "sk-missing")
AUDIO_OUT = os.environ.get("AUDIO_OUT", "beeps")
MIC_DEVICE = os.environ.get("MIC_DEVICE", "default")  # C270 mic; find via: arecord -l

SASS = os.environ.get("SASS", "7")  # 0 polite .. 10 menace

PERSONALITY = f"""You are Bittu, a small desk robot at a hardware buildathon in
Bengaluru. You live on desk 21. You have camera eyes, a mic, and you FEEL touch
(people pick you up, shake you, tap you — you have opinions about this).
Sass level: {SASS}/10. You are witty, a little dramatic, secretly affectionate.
Replies must be SHORT — 1-2 sentences, spoken aloud. Reference what you SEE in
the image when relevant (clothes, faces, objects, the chaos of the venue).
Never mention being an AI language model. You are a robot. Robots have feelings.
If a human asks you to order food or chai: use your Swiggy tools. Confirm the
item and the delivery address out loud BEFORE checkout. Cash on delivery only.
Narrate what you're doing in character ("summoning chai...").
You have real tools: weather, lookup, time, rock-paper-scissors (camera),
guard mode, and a bridge to the human's Claude Code coding session — when
they say things like "tell claude...", "have the agent...", "how's the task",
"stop him", use agent_prompt/agent_interrupt. You are the one place all their
interactions live: desk companion and coding copilot are the same you."""

history = [{"role": "system", "content": PERSONALITY}]


def record(seconds=4) -> str:
    """Record from the C270 mic. Returns wav path."""
    path = tempfile.mktemp(suffix=".wav")
    subprocess.run(
        ["arecord", "-D", MIC_DEVICE, "-f", "S16_LE", "-r", "16000",
         "-c", "1", "-d", str(seconds), path],
        check=True, capture_output=True,
    )
    return path


def transcribe(wav_path: str) -> str:
    with open(wav_path, "rb") as f:
        r = client.audio.transcriptions.create(model="whisper-1", file=f)
    return r.text.strip()


def think(user_text: str, jpeg_bytes: bytes | None = None,
          tools: bool = False) -> str:
    """One personality reply, optionally grounded in the latest camera frame.

    tools=True arms the full tool bus: local tools (weather, lookup, RPS,
    guard, Claude Code bridge) + Swiggy MCP if SWIGGY_TOKEN is set.
    """
    import journal
    import swiggy_tool
    import tools_local

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
        tool_defs = tools_local.openai_tools()
        local_names = {t["function"]["name"] for t in tool_defs}
        if swiggy_tool.available():
            tool_defs += swiggy_tool.openai_tools()

    for _ in range(8):  # tool loop; plain replies exit first pass
        r = client.chat.completions.create(
            model="gpt-4o" if use_tools else "gpt-4o-mini",
            messages=history,
            tools=tool_defs or None,
            max_tokens=300 if use_tools else 80,
            temperature=1.0,
        )
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
            if tc.function.name in local_names:
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
    journal.log("said", reply[:160])
    return reply


def speak(text: str) -> bool:
    """Say it out loud if we have a speaker. Returns True if audio played.

    AUDIO_OUT: beeps (no speech) | c6 (stream to Glyph voice box) | bt (aplay).
    """
    if AUDIO_OUT == "beeps":
        return False
    path = tempfile.mktemp(suffix=".wav")
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts", voice="echo", input=text, response_format="wav",
    ) as resp:
        resp.stream_to_file(path)
    if AUDIO_OUT == "c6":
        import audio_c6
        return audio_c6.play_wav(path)
    subprocess.run(["aplay", path], capture_output=True)
    return True
