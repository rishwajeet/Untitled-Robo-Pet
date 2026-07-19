# robot_body_faces.ino vs robot_body.ino

Standalone fork of `mcu/robot_body/robot_body.ino` with bitmap faces
(`assets/faces/generated/pet_faces.h`) wired into the eye renderer. Everything
that isn't eye *rendering* is byte-for-byte the same logic. Diff to eyeball:

## Functional differences

1. **`#include "pet_faces.h"`** added (copied into this folder — self-contained
   sketch, same convention as `robot_body/robot_body.ino`).

2. **`drawEyes()` rewritten** to draw a bitmap via `oled.drawBitmap(0, 0, bmp,
   PET_FACE_WIDTH, PET_FACE_HEIGHT, SSD1306_WHITE)` instead of procedural
   shapes, for every mood that has a face. Mapping (new `bitmapForMood()`):
   - `IDLE` -> `PET_FACE_IDLE`, or `PET_FACE_BLINK` during the existing blink window
   - `HAPPY` -> `PET_FACE_HAPPY`
   - `CURIOUS` -> `PET_FACE_WAITING`
   - `ANGRY` -> `PET_FACE_ERROR`
   - `SLEEPY` -> `PET_FACE_SLEEPING`
   - `SURPRISED` -> `PET_FACE_SURPRISED`
   - `DIZZY`, `LOVE` -> **unchanged**, still the original procedural X-eyes /
     heart-pupils drawing (no bitmap exists for these two).

3. **New agent-face override.** `{"c":"face","v":"claude_permission"}` (and
   the other five `claude_*` names) sets a global `agentFaceBitmap` pointer
   that takes priority over mood rendering. It is cleared only when a
   `{"c":"mood",...}` command arrives over serial — a local sensor-triggered
   mood change (button, shake, pickup, dark/light) does **not** clear it,
   since those go through `setMood()` while only the serial "mood" handler
   clears the override. Unrecognized face names are ignored (override
   untouched).

4. **Speaking preference.** While `overlayText` is active (a caption is
   showing) and no agent-face override is active, `PET_FACE_SPEAKING` is
   shown instead of the mood bitmap — the robot's mouth animates while it
   "talks," independent of whatever mood it was in.

5. **Caption clipping.** Bitmaps are full 128x32; the original code shrank
   the eye geometry to make room for the bottom caption line. The simplest
   correct equivalent for bitmaps: draw the full face, then
   `fillRect(0, 20, 128, 12, SSD1306_BLACK)` to blank the bottom 12 rows
   before printing the caption text — one code path for both bitmap and
   procedural (DIZZY/LOVE) rendering. Cost: a sliver of face art below row 20
   gets clipped whenever a caption is showing (see Risks below).

Everything else — serial protocol (`mood`/`text`/`beep`/now `face`), beep
patterns, `driveLeds()`, `sendEvent()`, `checkMotion()`, button handling, LDR
polling, mood auto-decay, and the boot screen — is unchanged from
`robot_body.ino`.

## pet_faces.h names vs. what was described

All ten companion names and all six `claude_*` names described matched the
actual header exactly — `grep -o 'PET_FACE_[A-Z_]*\[\]' pet_faces.h`:
`PET_FACE_IDLE`, `PET_FACE_HAPPY`, `PET_FACE_WORKING`, `PET_FACE_LISTENING`,
`PET_FACE_SPEAKING`, `PET_FACE_WAITING`, `PET_FACE_ERROR`,
`PET_FACE_SLEEPING`, `PET_FACE_SURPRISED`, `PET_FACE_BLINK`,
`PET_FACE_CLAUDE_DONE`, `PET_FACE_CLAUDE_NEEDS_INPUT`,
`PET_FACE_CLAUDE_PERMISSION`, `PET_FACE_CLAUDE_TOOL_RUNNING`,
`PET_FACE_CLAUDE_RATE_LIMITED`, `PET_FACE_CLAUDE_DISCONNECTED`. No renames
needed. `PET_FACE_WORKING` and `PET_FACE_LISTENING` exist in the header but
are unused here — there's no `Mood` value that maps to them (no "working" or
"listening" mood in the current enum).

## Risks / things to check before swapping this in

- **Not compiled.** No Arduino toolchain available on this box during this
  task — verified by static checks only (brace balance, every referenced
  `PET_FACE_*` name confirmed present in `pet_faces.h`, `drawBitmap` argument
  order matches the Adafruit_GFX signature `drawBitmap(x, y, bitmap, w, h,
  color)`). Build this in the Arduino IDE/CLI before flashing.
- **Caption clipping cuts into the `claude_*` art more than companion faces.**
  The companion faces (idle/happy/etc.) have their real content roughly in
  rows 5-30, so clipping at row 20 mostly loses a sliver near the bottom. The
  `claude_*` faces are full-body robot illustrations with content from row 1
  to row 31 (legs/base included) — if a caption is ever shown *while* an
  agent-face override is active, the bottom third of that illustration
  (the robot's legs) gets blacked out along with the caption band. Confirmed
  by decoding all 16 arrays and checking min/max non-zero row per face.
  Whether this combination (agent face + caption) actually happens depends
  on how `brain.py` sequences `face` vs `text` commands — see below.
- **`agentFaceBitmap` never times out on its own.** It only clears on the next
  serial `mood` command. If the brain sends a `face` command and then never
  sends a `mood`, the agent face is sticky forever (by design, per spec —
  but worth knowing if the brain's lifecycle doesn't reliably emit a mood
  command on every state transition).
- **Diffing against the flashed `robot_body.ino`**: once the live flash
  finishes, diff this file against the then-current `robot_body.ino` (not
  just the copy read during this task) in case the flashing process's guard
  edits changed anything outside of `drawEyes()`/serial handling — this fork
  only touched rendering + the `face` command, so a clean diff should show
  no overlap with typical guard-edit territory (pins, WiFi/board config,
  library includes unrelated to faces).

## Linux-side hook (not implemented — flagged for whoever wires it up)

`linux/brain.py` has an `AGENT_FX` dict (around `linux/brain.py:86-92`)
mapping Claude Code lifecycle events to `(mood, text)` tuples, e.g.
`"agent_working": ("curious", None)`. That's the natural place to also emit
`{"c":"face","v":"claude_tool_running"}` — e.g. extend each tuple with an
optional face name, or add a parallel small dict, and have the dispatch site
that currently does `link.mood(m)` / `link.text(t)` also call a new
`link.face(name)` when present. Not implemented here per the brief (don't
touch `linux/`).
