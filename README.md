# BITTU — desk robot with senses (Buildathon, Desk 21)

## STATUS — live, updated by the orchestrator session

**ARCHITECTURE DECISION (user call): the brain runs ON THE MAC, tethered.**
Best experience now; migrate to the board later via env vars if time allows.
The Q-side code paths are intact — they ARE the migration.

**PHYSICAL TOPOLOGY — one cable to the Mac, everything else ON the robot:**
```
MacBook ──single USB-C──> USB HUB (mounted on the robot rig)
                            ├── UNO Q data cable  (body: faces/LEDs/touch/buttons)
                            └── Logitech C270     (eyes + mic, aimed by the robot)
```
The Q's one port can't host the C270 while tethered — the HUB is mandatory
(event provides hubs; help desk if our kit lacks one). Mac sees both devices
directly: serial for the body, C270 for eyes/ears. Speaker: breadboard
speaker does MCU beeps; TTS voice plays from Mac speakers beside the robot.
UPGRADE if C6 pin answer arrives before ~3pm: Glyph C6 + speaker on the
breadboard, TTS streamed over hotspot (audio_c6.py -> glyph_audio.ino,
both ends already written).

| Piece | State |
|---|---|
| MCU sketch | **FLASHED & BOOTED** — `mcu/robot_body_faces/` (bitmap faces + `claude_*` agent faces) is ON the board. `mcu/robot_body/` = proven fallback, 30s reflash. |
| Wiring | in progress → follow **WIRING.md** (3.3V everywhere; wire first, reset after) |
| Serial protocol | flashed but unverified → serial test at bottom of WIRING.md proves it |
| Linux brain (`linux/`) | written + Mac-verified pieces; NOT yet deployed to the board (adb deploy in progress) |
| Dashboard `linux/dashboard.py` | verified on Mac — run on the Q, browse `:8302` |
| Claude Code bridge + hooks | **fully verified against real claude session** — runbook below; ROBOT_IP trap in bold |
| Glyph C6 audio | sketch ready, NOT flashed — need speaker pin/interface answer from help desk |
| Swiggy MCP | client written, untested — needs OTP token dance (do late afternoon) |
| Faces/animations assets | in repo (Hamza); bitmaps live on board, GIFs not yet used |

Compile/flash from THIS Mac works directly:
```bash
arduino-cli compile --fqbn arduino:zephyr:unoq mcu/robot_body_faces/robot_body_faces.ino
arduino-cli upload  --fqbn arduino:zephyr:unoq -p /dev/cu.usbmodemXXXX mcu/robot_body_faces/robot_body_faces.ino
# first upload sometimes logs "verify failed in bank" — run upload AGAIN; second pass is clean (stale-bank quirk)
```

**Flashing from ANY OTHER laptop needs 3 one-time things:**
1. `arduino-cli core install arduino:zephyr` (+ libs: Adafruit SSD1306, Adafruit GFX, Arduino_Modulino)
2. **Patch Adafruit_SSD1306.h** (~line 54, in the HAVE_PORTREG #if chain) — add:
   ```c
   #elif defined(ARDUINO_ARCH_ZEPHYR)
   #undef HAVE_PORTREG
   ```
   Without it the build explodes inside `gpio_lowlevel_stm32.h` (the lib's
   fast-SPI pin path is incompatible with the Zephyr core).
3. Include order in any new sketch: `Modulino.h` BEFORE the Adafruit headers
   (SSD1306's bare `WHITE`/`BLACK` macros mangle Modulino's color externs).

**Face assets ready** (`assets/faces/`): 128x32 1-bit bitmaps +
`pet_faces.h`, Adafruit_GFX-compatible. To use them in
`mcu/robot_body/robot_body.ino`: copy `pet_faces.h` next to the sketch,
`#include` it, and in `drawEyes()` replace the procedural drawing with
`oled.drawBitmap(0, 0, PET_FACE_<STATE>, 128, 32, 1)` per mood
(error→angry, waiting→curious; keep procedural dizzy/love — no bitmap yet).
The `claude_*` faces map to agent mode: permission→agent_ask,
tool_running→agent_working, done→agent_done. Keep the blink frame timing.

Sees (C270) · Hears (C270 mic) · **Feels** (Modulino movement) · Reacts (OLED
eyes + LED moods + beeps/voice). MCU has local reflexes (instant), Linux brain
adds wit (cloud). If WiFi dies mid-demo, the robot STILL reacts — reflexes are
on the MCU.

## Deploy (fastest path)

1. **MCU** — DONE (see STATUS). Reflash commands are in STATUS above.
   The flashed sketch alone = eyes + blink + touch reactions + beeps.
2. **Linux side** — copy `linux/` onto the UNO Q (scp or Hydron), then:
   `pip install -r requirements.txt`
   Full run (all optional except the first two):
   ```
   OPENAI_API_KEY=sk-...            \
   ROBOT_PORT=/dev/ttyACM0          \
   AUDIO_OUT=c6 C6_IP=<glyph-ip>    \  # or beeps / bt
   BRIDGE_URL=http://<laptop>:8400  \  # two-way Claude Code bridge
   SWIGGY_TOKEN=<token>             \  # food powers
   SASS=7 python3 brain.py
   ```
   Find the port: `ls /dev/tty*` before/after — or ask Hydron to wire
   `transport.py` to the UNO Q's Linux↔MCU serial bridge (only file that
   may need adapting).

## Wiring (breadboard)

| Part | Hookup |
|---|---|
| OLED 0.91" | VCC→3.3V, GND, SDA→A4, SCL→A5 (I2C addr 0x3C) |
| Modulino Movement | Qwiic cable → Qwiic port. Done. |
| Speaker | D9 → pot outer leg; pot **wiper** → speaker+; speaker− → GND. Pot = volume knob. Never bypass the pot (pin current). |
| Talk button | D2 → button → GND |
| Pet button | D3 → button → GND |
| Red LEDs | D5, D6 → long leg (through ~220Ω if any at help desk; else keep PWM low) |
| Blue LEDs | D10, D11 → same |
| LDR | 3.3V → LDR → A0, and A0 → 10K→ GND (no 10K? ask help desk; else skip LDR) |

## Heartbeat + journal — the aliveness engine

Bittu wakes every 30-90s (jittered), looks through the camera, reads his own
recent journal, and decides if anything is worth doing. Usually: nothing.
Occasionally: one line about what changed. All interactions — heard/said,
touches, tools, agent events, guard alerts — live in ONE journal
(`~/bittu-journal.jsonl` on the Q), so companion-mode and agent-mode are one
continuous being. `tail -f` it at the demo table — judges love seeing the
inner life scroll by.

Tools he can use by voice: weather, lookup (Wikipedia), time, rock-paper-
scissors vs the camera, guard mode ("guard my desk" → motion = alert + photo
of intruder), Swiggy, and the Claude Code bridge below.

## Two-way Claude Code bridge (talk to your coding session through him)

On the Mac: `tmux new -s claude` → run `claude` inside it. Then
`python3 laptop/bridge.py` (listens :8400). On the Q:
`export BRIDGE_URL=http://<laptop-ip>:8400`.
Now: "Bittu, tell claude to fix the tests" → prompt lands in the live
session. "Stop him" → Escape. Status flows back via hooks (below), and he
narrates it. Prompt in by voice, approve by button, result spoken back —
the robot IS the terminal.

## Mode 2 — agent peripheral (Claude Code drives the body)

`brain.py` now runs an HTTP server on **:8300**. Claude Code hooks curl it:
agent starts → curious eyes; working → status on OLED; done → happy + beep +
one smug spoken line; error → angry + red LEDs. And the killer beat:
`hooks/approve.sh` as a PreToolUse hook makes Claude **ask the robot for
permission** — talk button = allow, pet button = DENIED.

Setup: get the board's IP (`hostname -I`), replace ROBOT in
`hooks/settings-snippet.json`, merge into the demo project's
`.claude/settings.json` on the laptop. **The robot IP lives in TWO places:
the JSON's curl URLs AND `export ROBOT_IP=<ip>` before launching claude
(approve.sh reads the env var). Miss the second and approvals silently
fail-open — buttons never get asked.** Test with:
`curl -X POST http://<ip>:8300/event -d '{"e":"agent_done","text":"tests pass"}'`

**Network trap: venue WiFi often has client isolation (laptop can't reach
board). Test the curl EARLY. If blocked → phone hotspot with laptop + board
both on it. Decide this before 3pm, not at 4:45.**

## WHAPI WhatsApp webhook

The same port-8300 server accepts WHAPI callbacks at `/whatsapp-webhook`.
New incoming messages become brief OLED/beep notifications; outgoing messages,
delivery receipts, and other webhook events are acknowledged without interrupting
the robot. WHAPI's documented payload wraps new messages in `messages[]` with an
`event` of `messages.post`.

Run the receiver by itself on the machine behind ngrok:

```bash
python3 linux/server.py
```

The configured public callback is:

```text
https://tosha-unfaked-milena.ngrok-free.dev/whatsapp-webhook
```

Point the ngrok tunnel at local port `8300`, then check locally:

```bash
curl http://localhost:8300/whatsapp-webhook
```

For authentication, optionally set `WHAPI_WEBHOOK_SECRET` before starting the
server and configure WHAPI to send the same value in an `X-Webhook-Secret`
custom header. Requests are accepted without that header when the environment
variable is unset.

## Audio — Glyph C6 is the voice box (organizer-confirmed)

Flash `mcu/glyph_audio/glyph_audio.ino` on the Glyph C6 (board: "ESP32C6 Dev
Module", set hotspot SSID/PASS + speaker pins in the sketch — **ask help desk
which pins the speaker module uses and whether it's I2S or analog**). It
prints its IP on boot. On the Q: `C6_IP=<that ip> AUDIO_OUT=c6` and Bittu
speaks — TTS wav streams from the Q to the C6 over TCP :8301, out via I2S.
Fallbacks unchanged: `AUDIO_OUT=bt` (BT/USB speaker + aplay) or
`AUDIO_OUT=beeps` (R2-D2 mode: beeps + words on OLED — still charming).

## Swiggy MCP — Bittu orders real food (stretch, but REAL)

Swiggy has an official MCP server (food / Instamart / dineout), OAuth via
phone+OTP, **COD orders** — no payment code. Wired into the talk path:
say "order a chai to desk 21" → agent loop → real order.

1. Start Bittu's local server (`python3 linux/server.py`, or the normal brain).
2. On that machine, open `http://localhost:8300/swiggy/auth`, then complete
   phone + OTP. The callback stores the five-day access token in memory only.
3. Check `http://localhost:8300/swiggy/status`; `authenticated` should be true.
   Restarting requires logging in again. `SWIGGY_TOKEN` remains available as a
   non-interactive override for demo recovery.
Showmanship: place the real order ~4:40 so delivery lands DURING judging.
Do the OTP dance late afternoon (token freshness unknown). Instamart
(`SWIGGY_MCP=https://mcp.swiggy.com/im`) delivers in ~10 min — better for
demo timing than restaurant food.

## Demo script (rehearse 3x after 3:30)

1. Judge approaches → Bittu spots them, greets with an observation about them.
2. "Pick him up." → protest. 3. "Now shake him." → dizzy meltdown.
4. Pet/tap → forgives, hearts. 5. Hold TALK, ask him anything → sassy answer
   referencing what he sees. 6. MODE SWITCH: "he also has a job" — fire a
   Claude Code task on the laptop → Bittu tracks it, celebrates the finish,
   then Claude asks HIM for permission and a judge gets to press DENY.
Kill switch reality: what works at 4:30 is the demo — cut features, not sleep.

## Clock

- Before lunch: eyes on OLED + Modulino events printing (flash MCU alone).
- 2:00: serial link up, camera greet loop.  3:00: FULL LOOP demoable, ugly.
- 3:00 surprise: budget 30 min, architecture is modular — new input = one
  event name, new output = one command.
- 3:30–4:30: personality tuning (SASS env var + system prompt in voice.py),
  demo rehearsal. NOT new features.

## Name

He's BITTU (boot screen in the .ino, personality in voice.py). Change both
if the team hates it — but pick a name; judges remember names.
