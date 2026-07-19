#!/usr/bin/env python3
"""Generate animated 128x32 OLED faces, GIF previews, and C++ frame data."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

import generate_faces as faces


WIDTH, HEIGHT = faces.WIDTH, faces.HEIGHT
OUT = Path(__file__).resolve().parent / "generated" / "animations"
HEADER = Path(__file__).resolve().parent / "generated" / "pet_animations.h"


def working_frame(offset):
    image, draw = faces.canvas()
    faces.eye(draw, (25, 8, 57, 25), (41 + offset, 16))
    faces.eye(draw, (71, 8, 103, 25), (87 + offset, 16))
    draw.line((24, 5, 55, 8), fill=1, width=2)
    draw.line((73, 8, 104, 5), fill=1, width=2)
    return image


def listening_frame(wave):
    image, draw = faces.canvas()
    faces.eye(draw, (27, 7, 55, 25), (41, 16))
    faces.eye(draw, (73, 7, 101, 25), (87, 16))
    if wave >= 1:
        draw.arc((9, 10, 21, 22), 270, 90, fill=1, width=2)
        draw.arc((107, 10, 119, 22), 90, 270, fill=1, width=2)
    if wave >= 2:
        draw.arc((2, 6, 20, 26), 270, 90, fill=1, width=2)
        draw.arc((108, 6, 126, 26), 90, 270, fill=1, width=2)
    return image


def speaking_frame(size):
    image, draw = faces.canvas()
    faces.normal_eyes(draw, (42, 14), (86, 14))
    if size == 0:
        draw.line((60, 26, 68, 26), fill=1, width=2)
    elif size == 1:
        draw.ellipse((60, 23, 68, 29), outline=1, width=2)
    else:
        draw.ellipse((57, 20, 71, 30), outline=1, width=2)
    return image


def claude_done_frame(stage):
    image, draw = faces.canvas()
    faces.octopus(draw, "happy")
    if stage >= 1:
        end = (99, 20) if stage == 1 else (103, 24)
        draw.line((96, 17, *end), fill=1, width=3)
    if stage >= 2:
        end = (110, 16) if stage == 2 else (119, 6)
        draw.line((103, 24, *end), fill=1, width=3)
    return image


def question_frame(stage):
    image, draw = faces.canvas()
    faces.octopus(draw, "input")
    if stage >= 1:
        draw.arc((96, 4, 119, 22), 205, 75, fill=1, width=3)
    if stage >= 2:
        draw.line((118, 13, 109, 19), fill=1, width=3)
        draw.line((109, 19, 109, 22), fill=1, width=3)
    if stage >= 3:
        draw.rectangle((107, 27, 111, 30), fill=1)
    return image


def permission_frame(lit):
    image, draw = faces.canvas()
    faces.octopus(draw, "permission")
    if lit:
        draw.arc((99, 3, 117, 18), 180, 360, fill=1, width=3)
        draw.rounded_rectangle((96, 12, 120, 30), radius=3, outline=1, width=2)
        draw.ellipse((105, 17, 111, 23), fill=1)
        draw.line((108, 21, 108, 27), fill=1, width=2)
    else:
        draw.rounded_rectangle((100, 14, 116, 28), radius=2, outline=1)
    return image


def tool_frame(dot_count):
    image, draw = faces.canvas()
    faces.octopus(draw)
    for index, x in enumerate((96, 108, 120)):
        if index < dot_count:
            draw.ellipse((x - 3, 14, x + 2, 19), fill=1)
        else:
            draw.point((x, 17), fill=1)
    return image


def draw_six(draw, x, y):
    draw.line((x + 17, y, x + 4, y), fill=1, width=3)
    draw.line((x + 3, y + 1, x, y + 7), fill=1, width=3)
    draw.line((x, y + 7, x, y + 18), fill=1, width=3)
    draw.line((x + 2, y + 9, x + 15, y + 9), fill=1, width=3)
    draw.line((x + 16, y + 10, x + 16, y + 18), fill=1, width=3)
    draw.line((x + 15, y + 19, x + 2, y + 19), fill=1, width=3)


def draw_seven(draw, x, y):
    draw.line((x, y, x + 18, y), fill=1, width=3)
    draw.line((x + 18, y + 1, x + 12, y + 9), fill=1, width=3)
    draw.line((x + 12, y + 9, x + 8, y + 19), fill=1, width=3)


def draw_upturned_palm(draw, y, mirror=False):
    """Draw a side-profile hand with its cupped palm facing upward."""
    def point(x, y_value):
        return (127 - x if mirror else x, y_value)

    # One solid silhouette joins forearm, cupped palm, and extended fingers.
    hand = [
        point(0, y + 18), point(0, y + 14), point(9, y + 8),
        point(14, y + 6), point(29, y + 6), point(32, y + 8),
        point(29, y + 11), point(20, y + 12), point(13, y + 11),
        point(9, y + 12),
    ]
    draw.polygon(hand, fill=1)

    # A raised thumb above the flat palm makes the upward orientation explicit.
    thumb = [
        point(9, y + 9), point(12, y + 3), point(15, y + 1),
        point(19, y + 4), point(16, y + 7), point(13, y + 8),
    ]
    draw.polygon(thumb, fill=1)

    # Dark notches separate the fingers without weakening the silhouette.
    for x in (21, 25, 29):
        draw.line((*point(x, y + 6), *point(x - 1, y + 8)), fill=0)


def six_seven_frame(tilt):
    image, draw = faces.canvas()
    left_y = 2 + max(0, tilt)
    right_y = 2 + max(0, -tilt)
    draw_six(draw, 34, left_y)
    draw_seven(draw, 77, right_y)

    # Upturned palms rise and fall on opposite beats like the meme gesture.
    draw_upturned_palm(draw, 7 + tilt)
    draw_upturned_palm(draw, 7 - tilt, mirror=True)
    return image


ANIMATIONS = {
    "idle_blink": {
        "loop": True,
        "frames": [(faces.idle(), 1700), (faces.blink(), 90),
                   (faces.idle(), 110), (faces.blink(), 70), (faces.idle(), 1300)],
    },
    "working_scan": {
        "loop": True,
        "frames": [(working_frame(offset), 110) for offset in (-8, -4, 0, 4, 8, 4, 0, -4)],
    },
    "listening_pulse": {
        "loop": True,
        "frames": [(listening_frame(level), 170) for level in (0, 1, 2, 1)],
    },
    "speaking_mouth": {
        "loop": True,
        "frames": [(speaking_frame(size), 120) for size in (0, 1, 2, 1)],
    },
    "claude_done": {
        "loop": False,
        "frames": [(claude_done_frame(stage), duration)
                   for stage, duration in ((0, 100), (1, 90), (2, 90), (3, 700))],
    },
    "claude_needs_input": {
        "loop": True,
        "frames": [(question_frame(stage), duration)
                   for stage, duration in ((0, 180), (1, 130), (2, 130), (3, 650))],
    },
    "claude_permission": {
        "loop": True,
        "frames": [(permission_frame(lit), duration)
                   for lit, duration in ((False, 220), (True, 600), (False, 160), (True, 600))],
    },
    "claude_tool_running": {
        "loop": True,
        "frames": [(tool_frame(count), 220) for count in (1, 2, 3, 2)],
    },
    "meme_six_seven": {
        "loop": True,
        "frames": [(six_seven_frame(tilt), duration)
                   for tilt, duration in ((-3, 150), (0, 90), (3, 150), (0, 260))],
    },
}


def write_gif(name, animation):
    scale = 4
    color = "#D97757" if name.startswith("claude_") else "#67d9ff"
    previews = []
    durations = []
    for image, duration in animation["frames"]:
        enlarged = image.resize((WIDTH * scale, HEIGHT * scale), Image.Resampling.NEAREST)
        preview = Image.new("RGB", enlarged.size, "#071018")
        preview.paste(color, mask=enlarged)
        previews.append(preview)
        durations.append(duration)
    previews[0].save(
        OUT / f"{name}.gif",
        save_all=True,
        append_images=previews[1:],
        duration=durations,
        loop=0 if animation["loop"] else 1,
        disposal=2,
    )


def write_header():
    lines = [
        "// Generated by assets/faces/generate_animations.py. Do not edit.",
        "#pragma once",
        "#include <Arduino.h>",
        "",
        "struct PetAnimationFrame {",
        "  const uint8_t* bitmap;",
        "  uint16_t duration_ms;",
        "};",
        "",
        "struct PetAnimation {",
        "  const PetAnimationFrame* frames;",
        "  uint8_t frame_count;",
        "  bool loop;",
        "};",
        "",
    ]
    for animation_name, animation in ANIMATIONS.items():
        upper = animation_name.upper()
        for index, (image, _) in enumerate(animation["frames"]):
            data = faces.pack_bitmap(image)
            lines.append(f"const uint8_t PET_ANIM_{upper}_{index}[] PROGMEM = {{")
            for start in range(0, len(data), 16):
                chunk = ", ".join(f"0x{value:02X}" for value in data[start:start + 16])
                lines.append(f"  {chunk},")
            lines.extend(["};", ""])

        lines.append(f"const PetAnimationFrame PET_ANIM_{upper}_FRAMES[] = {{")
        for index, (_, duration) in enumerate(animation["frames"]):
            lines.append(f"  {{PET_ANIM_{upper}_{index}, {duration}}},")
        lines.extend([
            "};",
            f"const PetAnimation PET_ANIMATION_{upper} = {{",
            f"  PET_ANIM_{upper}_FRAMES,",
            f"  {len(animation['frames'])},",
            f"  {'true' if animation['loop'] else 'false'},",
            "};",
            "",
        ])
    HEADER.write_text("\n".join(lines))


def write_contact_sheet():
    scale = 2
    columns = 4
    margin = 8
    label_height = 16
    cell_width = WIDTH * scale
    cell_height = HEIGHT * scale
    sheet = Image.new(
        "RGB",
        (margin * 2 + columns * cell_width,
         margin + len(ANIMATIONS) * (label_height + cell_height)),
        "#17191c",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    y = margin
    for name, animation in ANIMATIONS.items():
        draw.text((margin, y), name.upper(), fill="#aeb7c2", font=font)
        y += label_height
        frames = animation["frames"]
        indices = [round(i * (len(frames) - 1) / (columns - 1)) for i in range(columns)]
        color = "#D97757" if name.startswith("claude_") else "#67d9ff"
        for column, index in enumerate(indices):
            image = frames[index][0].resize(
                (cell_width, cell_height), Image.Resampling.NEAREST)
            preview = Image.new("RGB", image.size, "#071018")
            preview.paste(color, mask=image)
            sheet.paste(preview, (margin + column * cell_width, y))
        y += cell_height
    sheet.save(OUT.parent / "animation-preview.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, animation in ANIMATIONS.items():
        write_gif(name, animation)
    write_header()
    write_contact_sheet()
    print(f"Generated {len(ANIMATIONS)} animations in {OUT}")


if __name__ == "__main__":
    main()
