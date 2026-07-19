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
import senses
import dashboard
import server
import tools_local
import voice
from emotions import EmotionDirector, PresenceTracker
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
    frame = senses.get_latest_frame()
    if frame is None:
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

def open_camera():
    cap = cv2.VideoCapture(senses.find_camera())
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


def grab_jpeg(cap) -> bytes | None:
    return senses.get_latest_jpeg()  # capture thread keeps this fresh


def count_faces(cap, cascade) -> int:
    if cascade is None:  # opencv build without CascadeClassifier -- presence
        return 0         # detection is a nice-to-have, not worth crashing over
    frame = senses.get_latest_frame()
    if frame is None:
        return 0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
    return len(faces)


def load_cascade():
    """None if this opencv build/data is missing Haar cascades (see
    requirements.txt) -- caller falls back to "nobody's ever present"."""
    try:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(path)
        if cascade.empty():
            print(f"face cascade missing/empty at {path} -- presence detection off")
            return None
        return cascade
    except AttributeError:
        print("cv2.CascadeClassifier unavailable in this opencv build -- "
              "presence detection off (see requirements.txt pin)")
        return None


def deliver(link, reply: str, display=None):
    """Speak if we can; always show on OLED; beep either way."""
    if display:
        display.caption(reply)
        display.activity("speaking")
    else:
        link.text(reply)
    try:
        spoke = voice.speak(reply)
    finally:
        if display:
            display.activity(None)
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


def greet_prompt(face: dict | None) -> str:
    """Known people get named + a callback to the journal; strangers get
    the existing generic observational greeting."""
    if not face or not face.get("known"):
        return EVENT_PROMPTS["greet"]
    notes = senses.person_notes(face["name"])
    notes_txt = ("What you remember about them: " + "; ".join(notes) + "\n") if notes else ""
    return (f"{face['name']} just walked back up to your desk — you "
            f"recognize them (visit #{face['times_seen']} today). "
            f"{notes_txt}Greet them BY NAME with a callback to something "
            f"you remember about them:\n{journal.recent(8)}")


def main():
    link = Link()
    display = EmotionDirector(link)
    cap = open_camera()
    senses.start_capture(cap)
    cascade = load_cascade()
    senses.report_identification_tier()

    agent_events = queue.Queue()
    server.start(agent_events)
    try:
        dashboard.start()
    except OSError as exc:
        print(f"Dashboard unavailable on :{dashboard.PORT}: {exc}")
    link.set_observer(server.record_hardware)
    server.update_runtime(robot=True, camera=cap.isOpened())
    tools_local.set_frame_source(lambda: grab_jpeg(cap))
    server.set_frame_source(senses.get_latest_jpeg)
    link.send("reinit")  # recover the OLED if a reflash/power blip wedged it

    display.base("idle")
    display.react("happy")
    display.caption("BITTU ONLINE")
    journal.log("system", "Bittu online")
    print("Bittu online. Ctrl-C to stop.")
    print(f"Dashboard: http://localhost:{dashboard.PORT}")

    presence = PresenceTracker()
    last_greet = 0.0
    last_api = 0.0
    next_beat = time.time() + 45
    guard_state = {}
    person_greeted = {}
    mode = "ambient"  # double-tap pet toggles "ambient" <-> "agent"
    current_person = None   # who's at the desk right now (refreshed ~45s)
    last_ident = 0.0
    listen_deadline = 0.0
    last_pet_at = 0.0
    last_talk_start = 0.0
    asleep = False  # name -> last spoken-greeting ts (30 min social memory)

    while True:
        # 0) Agent mode: Claude Code events from the HTTP server
        ctl_ev = None  # control-plane event that reuses the MCU-event paths below
        try:
            source, ae, atext = agent_events.get_nowait()
            journal.log(source, f"{ae}: {atext}")
            if source == "control":
                # Dashboard cockpit: typed chat, remote PTT, body commands, guard
                if ae == "say":
                    link.mood("curious")
                    try:
                        reply = voice.think(atext, grab_jpeg(cap), tools=True)
                        link.mood("happy")
                        deliver(link, reply)
                    except Exception as e:
                        print(f"say failed: {e}")
                elif ae == "listen":
                    ctl_ev = "talk"  # same flow as the physical talk button
                elif ae == "listen_stop":
                    ctl_ev = "talk_up"
                elif ae == "mode":
                    ctl_ev = "pet_double"
                elif ae == "sleep":
                    asleep = True
                    voice.record_stop()  # drop any open mic
                    display.base("sleepy")
                    display.caption("zzz...")
                    journal.log("system", "asleep — waiting for a wake word")
                elif ae == "command":
                    cmd = jsonlib.loads(atext)
                    link.send(cmd.get("c", ""), cmd.get("v", ""))
                elif ae == "guard":
                    tools_local.set_guard(atext)
                    link.text("guard: " + atext)
                elif ae == "web_answer":
                    link.mood("happy" if atext == "yes" else "angry")
                    link.text("approved!" if atext == "yes" else "DENIED.")
            elif source == "whatsapp":
                link.mood("curious")
                link.text(atext)
                link.beep("curious")
                try:  # announce sender + message out loud, in character
                    reply = voice.think(
                        f"A WhatsApp just arrived — '{atext}' (format is "
                        "sender: message). Announce WHO texted and WHAT they "
                        "said, verbatim, in one in-character line.")
                    deliver(link, reply, display)
                except Exception as e:
                    print(f"whatsapp announce failed: {e}")
            elif ae in ("agent_start", "agent_working") and mode == "ambient":
                pass  # routine agent noise stays silent in ambient mode (journaled above)
            else:
                m, default_text = AGENT_FX.get(ae, ("curious", None))
                link.mood(m)
                link.text(atext or default_text or "working...")
            if source == "agent" and ae == "agent_done":
                link.beep("happy")
                try:  # one witty spoken line about the finished task — the wow
                    deliver(link, voice.think(
                        f"Your human's coding agent just finished: '{atext}'. "
                        "One short smug line about it."))
                except Exception:
                    pass
            elif source == "agent" and ae == "agent_error":
                link.beep("angry")
            elif source == "agent" and ae == "agent_ask":
                link.beep("surprised")
        except queue.Empty:
            pass

        # 1) MCU events (touch, buttons) — highest priority
        ev = link.next_event(timeout=0.05) or ctl_ev
        if ev in ("dark", "light"):
            ev = None  # LDR cut from the build; ignore any stragglers

        # Asleep: everything suspended except a wake word via the talk button
        if asleep:
            if ev == "talk" and not voice.recording():
                try:
                    voice.record_start()
                except Exception:
                    pass
            elif voice.recording() and ev == "talk_up":
                try:
                    wav = voice.record_stop()
                    heard = voice.transcribe(wav) if wav else ""
                    print(f"(asleep) HEARD: {heard}")
                    if "wake" in heard.lower() or "good morning" in heard.lower():
                        asleep = False
                        display.base("idle")
                        journal.log("system", "WOKE UP")
                        reply = voice.think(
                            "You are being woken up in front of an audience "
                            "(possibly judges!). Yawn, stretch dramatically, "
                            "then greet the crowd with maximum charm — you "
                            "can see them in the image.", grab_jpeg(cap))
                        display.react("happy")
                        deliver(link, reply, display)
                except Exception as e:
                    print(f"wake attempt failed: {e}")
            time.sleep(0.05)
            continue

        # Voice-requested mode switch (set_mode tool) — consume the flag
        if tools_local.MODE_REQ["want"] and tools_local.MODE_REQ["want"] != mode:
            tools_local.MODE_REQ["want"] = None
            ev = "pet_double"
        elif tools_local.MODE_REQ["want"]:
            tools_local.MODE_REQ["want"] = None  # already in that mode

        # Brain-side double-tap detection: the firmware's blocking love-beep
        # (~400ms) eats its own 450ms double-tap window, so pet_double rarely
        # arrives from the MCU. Two pets within 1.5s count as a double here.
        if ev == "pet":
            if now - last_pet_at < 1.5:
                ev = "pet_double"
                last_pet_at = 0.0
            else:
                last_pet_at = now

        # Double-tap pet = mode toggle (agent <-> ambient)
        if ev == "pet_double":
            mode = "agent" if mode == "ambient" else "ambient"
            journal.log("system", f"mode -> {mode}")
            if mode == "agent":
                display.base("attentive")
                deliver(link, "Agent mode. Speak and I relay to Claude — say 'Bittu' first to talk to me.", display)
            else:
                display.base("idle")
                deliver(link, "Ambient mode. Just us again.", display)
            ev = None

        # Buttons answer a pending agent question instead of normal behavior
        if server.has_pending() and ev in ("talk", "pet"):
            server.put_answer("yes" if ev == "talk" else "no")
            link.mood("happy" if ev == "talk" else "angry")
            link.text("approved!" if ev == "talk" else "DENIED.")
            ev = None

        # 2) Presence via local face detect ~2Hz — free and fast
        now = time.time()
        greet_face = None
        n = count_faces(cap, cascade)
        presence_event = presence.update(n, now)
        if presence.present:
            if presence_event in ("arrived", "joined"):
                display.base("attentive")
                display.react("curious")
            # Desk-robot social model: he LIVES with his humans. Strangers get
            # a spoken greeting; a known person only gets one after a real
            # absence (30 min per-person memory). Otherwise he just *notices* —
            # happy face flick, journal line, no speech. He's a companion,
            # not a doorbell.
            if presence_event in ("arrived", "joined") and now - last_greet > 60:
                last_greet = now
                frame = senses.get_latest_frame()
                greet_face = senses.identify_person(frame, cascade) if frame is not None else None
                name = (greet_face or {}).get("name")
                if greet_face and greet_face.get("known"):
                    current_person = name
                    last_ident = now
                if greet_face and greet_face.get("known") and \
                        now - person_greeted.get(name, 0) < 1800:
                    journal.log("seen", f"{name} (still around — no re-greet)")
                    display.react("happy")  # silent acknowledgment
                else:
                    if name:
                        person_greeted[name] = now
                    if mode == "ambient":
                        ev = ev or "greet"
        elif presence_event == "left":
            display.base("sleepy")

        # 3) Hold-to-talk: button press starts the mic, release stops it.
        # (Cockpit LISTEN has no release event — auto-stops after 6s.)
        if ev == "talk":
            # Double-press on TALK = mode toggle (press-release-press < 1.2s).
            # Talk starts are instant/non-blocking, so unlike the pet button
            # nothing eats the detection window.
            if not voice.recording() and now - last_talk_start < 1.2:
                last_talk_start = 0.0
                ev = "pet_double"
            elif not voice.recording():
                last_talk_start = now
        if ev == "talk":
            if not voice.recording():
                display.caption("listening...")
                display.base("attentive")
                display.activity("listening")
                try:
                    voice.record_start()
                    listen_deadline = now + 28  # client/web release or button-up ends it sooner
                except Exception as e:
                    print(f"record start failed: {e}")
                    display.caption("ears broke :(")
                    display.activity(None)
            continue

        if voice.recording() and (ev == "talk_up" or now > listen_deadline):
            display.activity(None)
            try:
                wav = voice.record_stop()
                heard = voice.transcribe(wav) if wav else ""
                print(f"HEARD: {heard}")
                low = heard.lower() if heard else ""
                # Mode phrases NEVER relay — intercept before routing.
                if heard and "mode" in low and ("ambient" in low or "agent" in low):
                    tools_local.MODE_REQ["want"] = "agent" if "agent" in low else "ambient"
                    heard = ""
                if heard and mode == "agent" and not low.lstrip().startswith(
                        ("bittu", "britu", "bitu", "b2", "beetu", "bittoo", "bidu", "beto", "b-2", "bito")):
                    journal.log("heard", heard[:160])
                    result = tools_local.agent_prompt(heard)
                    journal.log("agent", f"relayed: {heard[:80]}")
                    display.react("curious")
                    deliver(link, "Sent to Claude. I'll narrate as it works.", display)
                elif heard:
                    speaker = current_person
                    if speaker:
                        heard = f"({speaker} is the one speaking to you.) {heard}"
                    reply = voice.think(heard, grab_jpeg(cap), tools=True)
                    display.react("happy")
                    deliver(link, reply, display)
                    if speaker:
                        voice.distill_note(speaker, heard, reply)
            except Exception as e:
                print(f"talk failed: {e}")
                display.caption("ears broke :(")
            continue

        # 4) Physical events -> witty reaction (rate-limited to stay snappy)
        if ev in EVENT_PROMPTS and now - last_api > 5:
            last_api = now
            journal.log("touch", ev)
            display.react(EVENT_MOODS[ev])
            try:
                prompt = greet_prompt(greet_face) if ev == "greet" else EVENT_PROMPTS[ev]
                reply = voice.think(prompt, grab_jpeg(cap))
                deliver(link, reply, display)
            except Exception as e:
                print(f"api failed: {e}")  # MCU already reacted locally — fine

        # 4.5) Continuous identity: know WHO is here, not just that someone is
        if presence.present and now - last_ident > 45:
            last_ident = now
            frame = senses.get_latest_frame()
            if frame is not None:
                try:
                    face = senses.identify_person(frame, cascade)
                    if face and face.get("known"):
                        if face["name"] != current_person:
                            journal.log("seen", f"{face['name']} is here")
                        current_person = face["name"]
                except Exception as e:
                    print(f"ident refresh failed: {e}")
        elif not presence.present:
            current_person = None

        # 5) Guard mode: watch for motion (~2Hz is plenty)
        if tools_local.GUARD["on"]:
            check_guard(link, cap, guard_state)

        # 6) Heartbeat: the aliveness engine, jittered 30-90s
        if now > next_beat:
            next_beat = now + random.uniform(30, 90)
            if not server.has_pending() and mode == "ambient":  # quiet focus in agent mode
                heartbeat(link, cap)

        time.sleep(0.03)


if __name__ == "__main__":
    main()
