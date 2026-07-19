# OLED faces

Original 128x32, 1-bit faces for the desktop pet. The deliberately heavy strokes
and simple silhouettes are designed to survive the OLED's low resolution.

Generate all assets:

```bash
python3 assets/faces/generate_faces.py
```

Outputs in `generated/`:

- Individual 128x32 monochrome PNG files for inspection and conversion.
- `face-preview.png`, enlarged 4x with nearest-neighbour scaling.
- `pet_faces.h`, row-packed, MSB-first bitmaps compatible with
  `Adafruit_GFX::drawBitmap()`.

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
