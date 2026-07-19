"""Bittu's brain — main loop. Run on the UNO Q Linux side:

    OPENAI_API_KEY=sk-... ROBOT_PORT=/dev/ttyACM0 AUDIO_OUT=beeps python3 brain.py

Wires together: camera presence (local, fast) + MCU events (touch, buttons)
+ OpenAI (only when there's something to say). Cheap local reflexes,
cloud only for wit — keeps it snappy on 2GB.
"""
import base64
import json as jsonlib
import queue
import random
import time

import cv2

import journal
import server
import tools_local
import voice
from transport import Link

HEARTBEAT_PROMPT = """You are Bittu's inner voice. Here is your recent life:

{journal}

You just woke for a heartbeat and glanced through your camera (image attached).
Decide if ANYTHING is worth doing. The bar is HIGH: a real change, something
new/funny/notable, or you haven't spoken in a long while and something deserves
comment. Repeating yourself is death. Boredom is fine — beings are mostly quiet.
Reply ONLY with JSON:
{{"action":"nothing"}} (the usual answer)
or {{"action":"say","text":"one short line","mood":"happy|curious|angry|sleepy|surprised|love"}}"""


def heartbeat(link, cap):
    """The aliveness engine: wake, look, usually do nothing."""
    jpeg = grab_jpeg(cap)
    if not jpeg:
        return
    b64 = base64.b64encode(jpeg).decode()
    try:
        r = voice.client.chat.completions.create(
            model="gpt-4o-mini", max_tokens=90,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text",
                 "text": HEARTBEAT_PROMPT.format(journal=journal.recent())},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                               "detail": "low"}}]}])
        d = jsonlib.loads(r.choices[0].message.content)
    except Exception as e:
        print(f"heartbeat failed: {e}")
        return
    if d.get("action") == "say" and d.get("text"):
        journal.log("heartbeat", d["text"][:160])
        link.mood(d.get("mood", "curious"))
        deliver(link, d["text"])
    else:
        journal.log("heartbeat", "(nothing worth doing)")


def check_guard(link, cap, state):
    """Motion at the desk while guard is on -> alert + photo + journal."""
    ok, frame = cap.read()
    if not ok:
        return
    gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
    if state.get("ref") is None:
        state["ref"] = gray
        return
    delta = cv2.absdiff(state["ref"], gray)
    state["ref"] = gray
    changed = (delta > 30).mean()
    if changed > 0.12 and time.time() - state.get("last", 0) > 10:
        state["last"] = time.time()
        path = f"/tmp/intruder-{int(time.time())}.jpg"
        cv2.imwrite(path, frame)
        journal.log("guard", f"MOTION DETECTED, photo {path}")
        link.mood("angry")
        link.beep("angry")
        link.text("INTRUDER ALERT")

# Agent mode: what each Claude Code lifecycle event looks like on the body.
AGENT_FX = {
    "agent_start":   ("curious",   "on it..."),
    "agent_working": ("curious",   None),        # text comes from the hook
    "agent_done":    ("happy",     "task done!"),
    "agent_error":   ("angry",     "it broke."),
    "agent_ask":     ("surprised", None),        # question text from /ask
}

CAM_INDEX = 0  # C270


def open_camera():
    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


def grab_jpeg(cap) -> bytes | None:
    ok, frame = cap.read()
    if not ok:
        return None
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes() if ok else None


def count_faces(cap, cascade) -> int:
    ok, frame = cap.read()
    if not ok:
        return 0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
    return len(faces)


def deliver(link, reply: str):
    """Speak if we can; always show on OLED; beep either way."""
    link.text(reply)
    spoke = voice.speak(reply)
    if not spoke:
        link.beep("curious")  # beep-voice mode: sound + text = the reply
    print(f"BITTU: {reply}")


# Situation prompts — the robot narrates its own body's events.
EVENT_PROMPTS = {
    "pickup":  "Someone just PICKED YOU UP off the desk. React. You can see them in the image.",
    "shake":   "Someone is SHAKING you. You are dizzy and offended. React.",
    "tap":     "Someone tapped/petted you. You secretly love it. React briefly.",
    "pet":     "Someone pressed your pet button. Pure affection. React briefly.",
    "dark":    "The lights went out / someone covered your eyes. React sleepy or spooked.",
    "greet":   "A new human just appeared in front of you. Greet them with one sharp observation about what you see.",
}

EVENT_MOODS = {"pickup": "surprised", "shake": "dizzy", "tap": "love",
               "pet": "love", "dark": "sleepy", "greet": "happy"}


def main():
    link = Link()
    cap = open_camera()
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    agent_events = queue.Queue()
    server.start(agent_events)
    tools_local.set_frame_source(lambda: grab_jpeg(cap))

    link.mood("happy")
    link.text("BITTU ONLINE")
    journal.log("system", "Bittu online")
    print("Bittu online. Ctrl-C to stop.")

    present = False
    last_seen = 0.0
    last_greet = 0.0
    last_api = 0.0
    next_beat = time.time() + 45
    guard_state = {}

    while True:
        # 0) Agent mode: Claude Code events from the HTTP server
        try:
            _, ae, atext = agent_events.get_nowait()
            journal.log("agent", f"{ae}: {atext}")
            m, default_text = AGENT_FX.get(ae, ("curious", None))
            link.mood(m)
            link.text(atext or default_text or "working...")
            if ae == "agent_done":
                link.beep("happy")
                try:  # one witty spoken line about the finished task — the wow
                    deliver(link, voice.think(
                        f"Your human's coding agent just finished: '{atext}'. "
                        "One short smug line about it."))
                except Exception:
                    pass
            elif ae == "agent_error":
                link.beep("angry")
            elif ae == "agent_ask":
                link.beep("surprised")
        except queue.Empty:
            pass

        # 1) MCU events (touch, buttons) — highest priority
        ev = link.next_event(timeout=0.05)

        # Buttons answer a pending agent question instead of normal behavior
        if server.has_pending() and ev in ("talk", "pet"):
            server.put_answer("yes" if ev == "talk" else "no")
            link.mood("happy" if ev == "talk" else "angry")
            link.text("approved!" if ev == "talk" else "DENIED.")
            ev = None

        # 2) Presence via local face detect ~2Hz — free and fast
        now = time.time()
        n = count_faces(cap, cascade)
        if n > 0:
            last_seen = now
            if not present and now - last_greet > 20:
                present = True
                last_greet = now
                ev = ev or "greet"
        elif present and now - last_seen > 6:
            present = False
            link.mood("sleepy")
            link.text("lonely...")

        # 3) Push-to-talk: record -> STT -> reply grounded in what it sees
        if ev == "talk":
            link.text("listening...")
            link.mood("curious")
            try:
                wav = voice.record(4)
                heard = voice.transcribe(wav)
                print(f"HEARD: {heard}")
                if heard:
                    reply = voice.think(heard, grab_jpeg(cap), tools=True)
                    link.mood("happy")
                    deliver(link, reply)
            except Exception as e:
                print(f"talk failed: {e}")
                link.text("ears broke :(")
            continue

        # 4) Physical events -> witty reaction (rate-limited to stay snappy)
        if ev in EVENT_PROMPTS and now - last_api > 5:
            last_api = now
            journal.log("touch", ev)
            link.mood(EVENT_MOODS[ev])
            try:
                reply = voice.think(EVENT_PROMPTS[ev], grab_jpeg(cap))
                deliver(link, reply)
            except Exception as e:
                print(f"api failed: {e}")  # MCU already reacted locally — fine

        # 5) Guard mode: watch for motion (~2Hz is plenty)
        if tools_local.GUARD["on"]:
            check_guard(link, cap, guard_state)

        # 6) Heartbeat: the aliveness engine, jittered 30-90s
        if now > next_beat:
            next_beat = now + random.uniform(30, 90)
            if not server.has_pending():  # never over an open question
                heartbeat(link, cap)

        time.sleep(0.03)


if __name__ == "__main__":
    main()
