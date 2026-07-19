#!/usr/bin/env python3
"""Generate 128x32 monochrome pet faces and Arduino-compatible bitmaps."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 128, 32
OUT = Path(__file__).resolve().parent / "generated"


def canvas():
    image = Image.new("1", (WIDTH, HEIGHT), 0)
    return image, ImageDraw.Draw(image)


def eye(draw, box, pupil=None):
    """A soft, high-contrast pet eye with a tiny catchlight."""
    draw.rounded_rectangle(box, radius=7, fill=1)
    if pupil:
        x, y = pupil
        draw.ellipse((x - 3, y - 4, x + 3, y + 4), fill=0)
        draw.point((x - 1, y - 2), fill=1)


def normal_eyes(draw, left=(42, 13), right=(86, 13)):
    eye(draw, (29, 3, 55, 23), left)
    eye(draw, (73, 3, 99, 23), right)


def cheeks(draw, y=23):
    """Two-pixel blush marks read well without color on the tiny OLED."""
    draw.line((19, y, 23, y), fill=1, width=2)
    draw.line((105, y, 109, y), fill=1, width=2)


def idle():
    image, draw = canvas()
    normal_eyes(draw)
    draw.arc((59, 20, 69, 28), 15, 165, fill=1, width=2)
    return image


def happy():
    image, draw = canvas()
    draw.arc((27, 3, 57, 23), 195, 345, fill=1, width=4)
    draw.arc((71, 3, 101, 23), 195, 345, fill=1, width=4)
    cheeks(draw, 22)
    draw.pieslice((56, 18, 72, 31), 5, 175, fill=1)
    draw.pieslice((59, 20, 69, 27), 5, 175, fill=0)
    return image


def working():
    image, draw = canvas()
    eye(draw, (29, 6, 55, 24), (46, 15))
    eye(draw, (73, 6, 99, 24), (90, 15))
    draw.line((28, 3, 53, 6), fill=1, width=2)
    draw.line((75, 6, 100, 3), fill=1, width=2)
    draw.line((59, 27, 69, 27), fill=1, width=2)
    return image


def listening():
    image, draw = canvas()
    eye(draw, (31, 5, 55, 24), (43, 14))
    eye(draw, (73, 5, 97, 24), (85, 14))
    draw.arc((5, 7, 22, 25), 270, 90, fill=1, width=2)
    draw.arc((106, 7, 123, 25), 90, 270, fill=1, width=2)
    draw.ellipse((61, 25, 67, 29), outline=1, width=2)
    return image


def speaking():
    image, draw = canvas()
    normal_eyes(draw, (42, 12), (86, 12))
    cheeks(draw, 23)
    draw.ellipse((57, 21, 71, 30), fill=1)
    draw.ellipse((60, 23, 68, 28), fill=0)
    return image


def waiting():
    image, draw = canvas()
    normal_eyes(draw, (38, 15), (82, 15))
    draw.arc((55, 23, 69, 30), 195, 345, fill=1, width=2)
    draw.point((106, 6), fill=1)
    draw.ellipse((111, 2, 115, 6), outline=1)
    return image


def error():
    image, draw = canvas()
    draw.polygon(((28, 7), (55, 12), (52, 23), (32, 22)), fill=1)
    draw.polygon(((73, 12), (100, 7), (96, 22), (76, 23)), fill=1)
    draw.ellipse((42, 14, 48, 20), fill=0)
    draw.ellipse((80, 14, 86, 20), fill=0)
    draw.arc((55, 23, 73, 32), 195, 345, fill=1, width=3)
    return image


def sleeping():
    image, draw = canvas()
    draw.arc((27, 7, 57, 23), 15, 165, fill=1, width=4)
    draw.arc((71, 7, 101, 23), 15, 165, fill=1, width=4)
    draw.arc((58, 22, 70, 29), 15, 165, fill=1, width=2)
    draw.text((104, 0), "z", fill=1, font=ImageFont.load_default())
    draw.text((113, 7), "Z", fill=1, font=ImageFont.load_default())
    return image


def surprised():
    image, draw = canvas()
    eye(draw, (28, 1, 56, 25), (42, 12))
    eye(draw, (72, 1, 100, 25), (86, 12))
    draw.ellipse((59, 23, 69, 31), fill=1)
    draw.ellipse((62, 25, 66, 29), fill=0)
    return image


def blink():
    image, draw = canvas()
    draw.arc((28, 8, 56, 21), 15, 165, fill=1, width=4)
    draw.arc((72, 8, 100, 21), 15, 165, fill=1, width=4)
    cheeks(draw, 22)
    draw.arc((59, 20, 69, 28), 15, 165, fill=1, width=2)
    return image


def octopus(draw, mood="normal"):
    """Draw the angular Claude notification mascot in the left 90 pixels."""
    # A hard-edged chamfered visor stays rectangular without looking generic.
    outline = ((8, 4), (12, 1), (80, 1), (84, 4),
               (84, 21), (80, 24), (12, 24), (8, 21), (8, 4))
    draw.line(outline, fill=1, width=2, joint="curve")
    draw.line((18, 5, 74, 5), fill=1)

    if mood == "happy":
        draw.arc((19, 8, 39, 20), 200, 340, fill=1, width=2)
        draw.arc((53, 8, 73, 20), 200, 340, fill=1, width=2)
    elif mood == "sleepy":
        draw.line((20, 15, 38, 15), fill=1, width=2)
        draw.line((54, 15, 72, 15), fill=1, width=2)
    elif mood == "sad":
        draw.line((21, 13, 28, 16), fill=1, width=2)
        draw.line((28, 16, 36, 13), fill=1, width=2)
        draw.line((56, 13, 64, 16), fill=1, width=2)
        draw.line((64, 16, 71, 13), fill=1, width=2)
    else:
        # Input/permission states glance at their glyph instead of staring ahead.
        pupil_shift = 2 if mood in {"input", "permission"} else 0
        draw.rounded_rectangle((24 + pupil_shift, 10, 30 + pupil_shift, 17), radius=2, fill=1)
        draw.rounded_rectangle((58 + pupil_shift, 10, 64 + pupil_shift, 17), radius=2, fill=1)

    # Four independent angular feet read as tentacles even at native resolution.
    draw.line((17, 24, 14, 28, 8, 28), fill=1, width=2)
    draw.line((36, 24, 33, 30, 27, 30), fill=1, width=2)
    draw.line((56, 24, 59, 30, 65, 30), fill=1, width=2)
    draw.line((75, 24, 78, 28, 84, 28), fill=1, width=2)
    draw.point((7, 28), fill=1)
    draw.point((85, 28), fill=1)


def claude_done():
    image, draw = canvas()
    octopus(draw, "happy")
    draw.line((96, 17, 103, 24), fill=1, width=3)
    draw.line((103, 24, 119, 6), fill=1, width=3)
    return image


def claude_needs_input():
    image, draw = canvas()
    octopus(draw, "input")
    draw.arc((96, 4, 119, 22), 205, 75, fill=1, width=3)
    draw.line((118, 13, 109, 19), fill=1, width=3)
    draw.line((109, 19, 109, 22), fill=1, width=3)
    draw.rectangle((107, 27, 111, 30), fill=1)
    return image


def claude_permission():
    image, draw = canvas()
    octopus(draw, "permission")
    draw.arc((99, 3, 117, 18), 180, 360, fill=1, width=3)
    draw.rounded_rectangle((96, 12, 120, 30), radius=3, outline=1, width=2)
    draw.ellipse((105, 17, 111, 23), fill=1)
    draw.line((108, 21, 108, 27), fill=1, width=2)
    return image


def claude_tool_running():
    image, draw = canvas()
    octopus(draw)
    draw.ellipse((94, 14, 99, 19), fill=1)
    draw.ellipse((105, 14, 110, 19), fill=1)
    draw.ellipse((116, 14, 121, 19), fill=1)
    return image


def claude_rate_limited():
    image, draw = canvas()
    octopus(draw, "sleepy")
    draw.line((97, 4, 119, 4), fill=1, width=2)
    draw.line((97, 29, 119, 29), fill=1, width=2)
    draw.line((99, 6, 117, 27), fill=1, width=2)
    draw.line((117, 6, 99, 27), fill=1, width=2)
    draw.polygon(((101, 7), (115, 7), (108, 14)), fill=1)
    draw.polygon(((108, 20), (101, 27), (115, 27)), fill=1)
    return image


def claude_disconnected():
    image, draw = canvas()
    octopus(draw, "sad")
    draw.arc((96, 8, 122, 27), 205, 335, fill=1, width=2)
    draw.line((92, 4, 124, 29), fill=1, width=3)
    return image


FACES = {
    "idle": idle,
    "happy": happy,
    "working": working,
    "listening": listening,
    "speaking": speaking,
    "waiting": waiting,
    "error": error,
    "sleeping": sleeping,
    "surprised": surprised,
    "blink": blink,
    "claude_done": claude_done,
    "claude_needs_input": claude_needs_input,
    "claude_permission": claude_permission,
    "claude_tool_running": claude_tool_running,
    "claude_rate_limited": claude_rate_limited,
    "claude_disconnected": claude_disconnected,
}


def pack_bitmap(image):
    """Pack rows MSB-first for Adafruit_GFX drawBitmap()."""
    data = []
    for y in range(HEIGHT):
        for x0 in range(0, WIDTH, 8):
            byte = 0
            for bit in range(8):
                if image.getpixel((x0 + bit, y)):
                    byte |= 1 << (7 - bit)
            data.append(byte)
    return data


def write_header(images):
    lines = [
        "// Generated by assets/faces/generate_faces.py. Do not edit.",
        "#pragma once",
        "#include <Arduino.h>",
        "",
        f"constexpr uint8_t PET_FACE_WIDTH = {WIDTH};",
        f"constexpr uint8_t PET_FACE_HEIGHT = {HEIGHT};",
        "",
    ]
    for name, image in images.items():
        data = pack_bitmap(image)
        lines.append(f"const uint8_t PET_FACE_{name.upper()}[] PROGMEM = {{")
        for start in range(0, len(data), 16):
            chunk = ", ".join(f"0x{value:02X}" for value in data[start:start + 16])
            lines.append(f"  {chunk},")
        lines.extend(["};", ""])
    (OUT / "pet_faces.h").write_text("\n".join(lines))


def write_preview(images):
    scale = 4
    label_height = 18
    margin = 8
    sheet = Image.new("RGB", (WIDTH * scale + margin * 2,
                              len(images) * (HEIGHT * scale + label_height) + margin),
                      "#17191c")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    y = margin
    for name, image in images.items():
        draw.text((margin, y), name.upper(), fill="#aeb7c2", font=font)
        y += label_height
        enlarged = image.resize((WIDTH * scale, HEIGHT * scale), Image.Resampling.NEAREST)
        rgb = Image.new("RGB", enlarged.size, "#071018")
        color = "#D97757" if name.startswith("claude_") else "#67d9ff"
        rgb.paste(color, mask=enlarged)
        sheet.paste(rgb, (margin, y))
        y += HEIGHT * scale
    sheet.save(OUT / "face-preview.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    images = {name: factory() for name, factory in FACES.items()}
    for name, image in images.items():
        image.save(OUT / f"{name}.png")
    write_header(images)
    write_preview(images)
    print(f"Generated {len(images)} faces in {OUT}")


if __name__ == "__main__":
    main()
