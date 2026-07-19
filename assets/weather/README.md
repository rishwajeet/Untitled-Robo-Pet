# OLED weather UI

Animated 40x32 one-bit icons designed for the left side of the 128x32 OLED.
The remaining 88 pixels display live temperature, precipitation probability,
and a compact condition label.

Generate the assets:

```bash
python3 assets/weather/generate_weather.py
```

Conditions: clear, partly cloudy, cloudy, rain, heavy rain, storm, snow, fog,
and wind. The generated C++ arrays are in `generated/weather_icons.h`; enlarged
GIF previews are in `generated/animations/`.

`firmware/uno_q_mcu/WeatherDisplay.h` renders dynamic values with the icons.
