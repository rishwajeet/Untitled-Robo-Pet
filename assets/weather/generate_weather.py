#!/usr/bin/env python3
"""Generate animated 40x32 monochrome weather icons for the OLED UI."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 40, 32
OUT = Path(__file__).resolve().parent / "generated"
GIF_OUT = OUT / "animations"


def canvas():
    image = Image.new("1", (WIDTH, HEIGHT), 0)
    return image, ImageDraw.Draw(image)


def draw_sun(draw, cx=18, cy=15, phase=0):
    draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=1, width=2)
    rays = [
        ((cx, cy - 13), (cx, cy - 10)),
        ((cx, cy + 10), (cx, cy + 13)),
        ((cx - 13, cy), (cx - 10, cy)),
        ((cx + 10, cy), (cx + 13, cy)),
        ((cx - 9, cy - 9), (cx - 7, cy - 7)),
        ((cx + 7, cy - 7), (cx + 9, cy - 9)),
        ((cx - 9, cy + 9), (cx - 7, cy + 7)),
        ((cx + 7, cy + 7), (cx + 9, cy + 9)),
    ]
    for index, (start, end) in enumerate(rays):
        if (index + phase) % 2 == 0:
            draw.line((*start, *end), fill=1, width=2)
        else:
            draw.point(start, fill=1)


def draw_cloud(draw, x=4, y=10, width=31):
    draw.ellipse((x + 2, y + 5, x + 16, y + 18), fill=1)
    draw.ellipse((x + 10, y, x + 25, y + 18), fill=1)
    draw.ellipse((x + 20, y + 6, x + width, y + 18), fill=1)
    draw.rectangle((x + 5, y + 11, x + width - 3, y + 18), fill=1)


def clear_frame(phase):
    image, draw = canvas()
    draw_sun(draw, 20, 16, phase)
    return image


def partly_cloudy_frame(offset):
    image, draw = canvas()
    draw_sun(draw, 12, 11, offset % 2)
    draw_cloud(draw, 7 + offset, 11, 30)
    return image


def cloudy_frame(offset):
    image, draw = canvas()
    draw_cloud(draw, 1 + offset, 8, 27)
    draw_cloud(draw, 9 - offset, 12, 29)
    return image


def rain_frame(offset, heavy=False):
    image, draw = canvas()
    draw_cloud(draw, 3, 4, 32)
    drops = ((10, 24), (20, 27), (30, 24))
    if heavy:
        drops += ((15, 29), (25, 29))
    for x, y in drops:
        shifted_y = 23 + ((y - 23 + offset) % 9)
        draw.line((x, shifted_y, x - 2, min(31, shifted_y + 3)), fill=1, width=2)
    return image


def storm_frame(flash):
    image, draw = canvas()
    draw_cloud(draw, 3, 3, 32)
    if flash:
        draw.polygon(((21, 19), (16, 26), (20, 26), (17, 32), (27, 23), (22, 23)), fill=1)
    else:
        draw.line((11, 23, 9, 28), fill=1, width=2)
        draw.line((31, 23, 29, 28), fill=1, width=2)
    return image


def snow_frame(offset):
    image, draw = canvas()
    draw_cloud(draw, 3, 3, 32)
    for index, (x, y) in enumerate(((10, 24), (20, 28), (30, 24))):
        shifted_y = 23 + ((y - 23 + offset + index) % 8)
        draw.line((x - 2, shifted_y, x + 2, shifted_y), fill=1)
        draw.line((x, shifted_y - 2, x, shifted_y + 2), fill=1)
    return image


def fog_frame(offset):
    image, draw = canvas()
    draw_cloud(draw, 7, 2, 27)
    for index, y in enumerate((21, 26, 31)):
        shift = offset if index % 2 == 0 else -offset
        draw.line((3 + shift, y, 31 + shift, y), fill=1, width=2)
    return image


def wind_frame(offset):
    image, draw = canvas()
    for index, (y, length) in enumerate(((8, 28), (16, 35), (25, 25))):
        shift = (offset + index * 2) % 6
        draw.line((2 + shift, y, length, y), fill=1, width=2)
        draw.arc((length - 7, y - 5, length + 3, y + 5), 270, 90, fill=1, width=2)
    return image


ANIMATIONS = {
    "clear": [(clear_frame(phase), 350) for phase in (0, 1)],
    "partly_cloudy": [(partly_cloudy_frame(offset), 450) for offset in (0, 1, 2, 1)],
    "cloudy": [(cloudy_frame(offset), 500) for offset in (0, 1, 2, 1)],
    "rain": [(rain_frame(offset), 180) for offset in (0, 2, 4, 6)],
    "heavy_rain": [(rain_frame(offset, True), 140) for offset in (0, 2, 4, 6)],
    "storm": [(storm_frame(flash), duration) for flash, duration in ((False, 350), (True, 120), (False, 160), (True, 120))],
    "snow": [(snow_frame(offset), 220) for offset in (0, 2, 4, 6)],
    "fog": [(fog_frame(offset), 450) for offset in (0, 2, 4, 2)],
    "wind": [(wind_frame(offset), 180) for offset in (0, 2, 4, 2)],
}


def pack_bitmap(image):
    data = []
    for y in range(HEIGHT):
        for x0 in range(0, WIDTH, 8):
            byte = 0
            for bit in range(8):
                if image.getpixel((x0 + bit, y)):
                    byte |= 1 << (7 - bit)
            data.append(byte)
    return data


def preview_frame(image, scale=4):
    enlarged = image.resize((WIDTH * scale, HEIGHT * scale), Image.Resampling.NEAREST)
    preview = Image.new("RGB", enlarged.size, "#071018")
    preview.paste("#67d9ff", mask=enlarged)
    return preview


def write_gifs():
    GIF_OUT.mkdir(parents=True, exist_ok=True)
    for name, frames in ANIMATIONS.items():
        previews = [preview_frame(image) for image, _ in frames]
        previews[0].save(
            GIF_OUT / f"{name}.gif",
            save_all=True,
            append_images=previews[1:],
            duration=[duration for _, duration in frames],
            loop=0,
            disposal=2,
        )


def write_header():
    lines = [
        "// Generated by assets/weather/generate_weather.py. Do not edit.",
        "#pragma once",
        "#include <Arduino.h>",
        "",
        f"constexpr uint8_t WEATHER_ICON_WIDTH = {WIDTH};",
        f"constexpr uint8_t WEATHER_ICON_HEIGHT = {HEIGHT};",
        "",
        "struct WeatherIconFrame {",
        "  const uint8_t* bitmap;",
        "  uint16_t duration_ms;",
        "};",
        "",
        "struct WeatherIconAnimation {",
        "  const WeatherIconFrame* frames;",
        "  uint8_t frame_count;",
        "};",
        "",
    ]
    for name, frames in ANIMATIONS.items():
        upper = name.upper()
        for index, (image, _) in enumerate(frames):
            data = pack_bitmap(image)
            lines.append(f"const uint8_t WEATHER_{upper}_{index}[] PROGMEM = {{")
            for start in range(0, len(data), 16):
                chunk = ", ".join(f"0x{value:02X}" for value in data[start:start + 16])
                lines.append(f"  {chunk},")
            lines.extend(["};", ""])
        lines.append(f"const WeatherIconFrame WEATHER_{upper}_FRAMES[] = {{")
        for index, (_, duration) in enumerate(frames):
            lines.append(f"  {{WEATHER_{upper}_{index}, {duration}}},")
        lines.extend([
            "};",
            f"const WeatherIconAnimation WEATHER_ANIMATION_{upper} = {{",
            f"  WEATHER_{upper}_FRAMES, {len(frames)}",
            "};",
            "",
        ])
    (OUT / "weather_icons.h").write_text("\n".join(lines))


def write_contact_sheet():
    scale = 2
    panel_width, panel_height = 256, 64
    label_height = 14
    margin = 8
    sheet = Image.new("RGB", (panel_width * 3 + margin * 2,
                              (panel_height + label_height) * 3 + margin), "#17191c")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (name, frames) in enumerate(ANIMATIONS.items()):
        column, row = index % 3, index // 3
        x = margin + column * panel_width
        y = margin + row * (panel_height + label_height)
        draw.text((x, y), name.upper().replace("_", " "), fill="#aeb7c2", font=font)
        icon = preview_frame(frames[min(1, len(frames) - 1)][0], 2)
        panel = Image.new("RGB", (panel_width, panel_height), "#071018")
        panel.paste(icon, (0, 0))
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.text((86, 7), "24 C", fill="#67d9ff", font=font, stroke_width=1)
        panel_draw.text((202, 7), "R70%", fill="#67d9ff", font=font)
        panel_draw.text((86, 44), name.upper().replace("_", " ")[:14], fill="#67d9ff", font=font)
        sheet.paste(panel, (x, y + label_height))
    sheet.save(OUT / "weather-ui-preview.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write_gifs()
    write_header()
    write_contact_sheet()
    print(f"Generated {len(ANIMATIONS)} weather animations in {OUT}")


if __name__ == "__main__":
    main()
