# OLED faces

Original 128x32, 1-bit faces for the desktop pet. The deliberately heavy strokes
and simple silhouettes are designed to survive the OLED's low resolution.

Generate all assets:

```bash
python3 assets/faces/generate_faces.py
python3 assets/faces/generate_animations.py
```

Outputs in `generated/`:

- Individual 128x32 monochrome PNG files for inspection and conversion.
- `face-preview.png`, enlarged 4x with nearest-neighbour scaling.
- `pet_faces.h`, row-packed, MSB-first bitmaps compatible with
  `Adafruit_GFX::drawBitmap()`.
- `animations/*.gif`, enlarged animated previews.
- `animation-preview.png`, four key frames from every animation.
- `pet_animations.h`, frame timing and bitmap data for the non-blocking firmware
  player in `firmware/uno_q_mcu/PetFaceAnimator.h`.

Arduino usage:

```cpp
display.clearDisplay();
display.drawBitmap(0, 0, PET_FACE_HAPPY, PET_FACE_WIDTH, PET_FACE_HEIGHT, 1);
display.display();
```

`blink` is intended as an animation frame: show it for roughly 80–120 ms, then
return to the previous expression.

Claude-specific status faces:

Claude states share an original chamfered rectangular robot-octopus mascot with
four separate angular tentacle-feet. This makes them recognizable on the monochrome OLED without relying
on text or color. The preview renders these faces in a Claude-inspired orange;
the physical 1-bit OLED will render the same pixels in its native color.

| Face | Meaning |
| --- | --- |
| `claude_done` | Task completed successfully |
| `claude_needs_input` | Claude is waiting for a user response |
| `claude_permission` | A tool or command needs approval |
| `claude_tool_running` | Claude is actively using a tool |
| `claude_rate_limited` | Work is paused by a usage or rate limit |
| `claude_disconnected` | The laptop client or Claude session disconnected |

Animation packs currently include idle blink, working scan, listening pulse,
speaking mouth, Claude done, Claude needs input, Claude permission, and Claude
tool activity. `meme_six_seven` adds a playful full-screen `6`/`7` bounce with
alternating palms. The notification animations can restore the current base loop
when they finish.
