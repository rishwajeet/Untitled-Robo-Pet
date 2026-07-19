#!/usr/bin/env python3
"""Generate representative previews of the 128x32 OLED message UI."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 128, 32
OUT = Path(__file__).resolve().parent / "generated"
FONT = ImageFont.load_default()


def clean(text):
    return " ".join(text.split()).encode("ascii", "replace").decode()


def wrap_pages(message, columns=21):
    words = clean(message).split()
    lines = []
    line = ""
    for word in words:
        while len(word) > columns:
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:columns])
            word = word[columns:]
        candidate = f"{line} {word}".strip()
        if len(candidate) <= columns:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line or not lines:
        lines.append(line)
    return [lines[index:index + 2] for index in range(0, len(lines), 2)]


def render(sender, message, page=0, icon_filled=False):
    image = Image.new("1", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(image)
    if icon_filled:
        draw.rounded_rectangle((0, 0, 10, 7), radius=2, fill=1)
        draw.polygon(((2, 6), (2, 10), (5, 7)), fill=1)
    else:
        draw.rounded_rectangle((0, 0, 10, 7), radius=2, outline=1)
        draw.line((2, 7, 2, 10, 5, 7), fill=1)

    pages = wrap_pages(message)
    page %= len(pages)
    draw.text((14, 0), clean(sender)[:14], fill=1, font=FONT)
    if len(pages) > 1:
        counter = f"{page + 1}/{len(pages)}"
        draw.text((128 - len(counter) * 6, 0), counter, fill=1, font=FONT)
    draw.line((0, 11, 127, 11), fill=1)
    for index, line in enumerate(pages[page]):
        draw.text((0, 12 + index * 10), line, fill=1, font=FONT)
    return image


def colorize(image, scale=4):
    enlarged = image.resize((WIDTH * scale, HEIGHT * scale), Image.Resampling.NEAREST)
    preview = Image.new("RGB", enlarged.size, "#071018")
    preview.paste("#67d9ff", mask=enlarged)
    return preview


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    examples = [
        ("Hamza", "Hi"),
        ("Build Team", "Claude finished the weather integration. Want me to deploy it now?"),
        ("Gerald", "[voice message]"),
    ]

    rows = []
    for sender, message in examples:
        pages = wrap_pages(message)
        rows.append(colorize(render(sender, message, min(1, len(pages) - 1)), 3))
    sheet = Image.new("RGB", (WIDTH * 3, HEIGHT * 3 * len(rows)), "#17191c")
    for index, row in enumerate(rows):
        sheet.paste(row, (0, index * HEIGHT * 3))
    sheet.save(OUT / "message-ui-preview.png")

    frames = [colorize(render("Hamza", "Hi", 0, filled)) for filled in (True, False, True, False)]
    frames[0].save(
        OUT / "message-arrival.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[120, 120, 120, 500],
        loop=0,
        disposal=2,
    )
    print(f"Generated message UI previews in {OUT}")


if __name__ == "__main__":
    main()
