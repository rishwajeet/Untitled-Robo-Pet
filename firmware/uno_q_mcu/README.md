# UNO Q OLED animation demo

Non-blocking 128x32 SSD1306 animation playback for the UNO Q microcontroller.
The demo rotates through idle, working, Claude done, and Claude tool-running
states every five seconds. Replace those timed transitions with Bridge commands
when the Linux pet service is added.

Dependencies:

```bash
arduino-cli lib install "Adafruit GFX Library" "Adafruit SSD1306"
```

Compile for the UNO Q:

```bash
arduino-cli compile --fqbn arduino:zephyr:unoq firmware/uno_q_mcu
```

The example uses the default `Wire` I2C bus and OLED address `0x3C`. Confirm the
address for the actual module before uploading. `PetFaceAnimator::update()` must
be called on every `loop()` iteration; it does not use delays, so input handling
and Bridge traffic can run alongside it.

Typical state calls:

```cpp
face.setBase(PET_ANIMATION_WORKING_SCAN, millis());
face.setBase(PET_ANIMATION_LISTENING_PULSE, millis());
face.setBase(PET_ANIMATION_SPEAKING_MOUTH, millis());
face.play(PET_ANIMATION_CLAUDE_DONE, true, millis());
face.setBase(PET_ANIMATION_CLAUDE_NEEDS_INPUT, millis());
face.setBase(PET_ANIMATION_CLAUDE_PERMISSION, millis());
face.setBase(PET_ANIMATION_CLAUDE_TOOL_RUNNING, millis());
face.play(PET_ANIMATION_MEME_SIX_SEVEN, true, millis());
```

## Weather display

`WeatherDisplay.h` combines animated condition icons with live readings:

```cpp
WeatherDisplay weather(display);
WeatherReading reading{243, 70, "RAIN"};  // 24.3 C, 70% precipitation
weather.show(WEATHER_ANIMATION_RAIN, reading, millis());

// Call alongside the other non-blocking updates.
weather.update(millis());
```

Available icon animations are `CLEAR`, `PARTLY_CLOUDY`, `CLOUDY`, `RAIN`,
`HEAVY_RAIN`, `STORM`, `SNOW`, `FOG`, and `WIND`.

## Message display

`MessageDisplay.h` provides a source-independent notification screen. The
downstream webhook processor only supplies sender and message text:

```cpp
MessageDisplay messages(display);
messages.show("Hamza", "Claude finished the task. Review it now?", millis());
messages.update(millis());  // call on every loop
```

The first 480 ms pulses the chat icon. Messages are sanitized to printable
ASCII, wrapped across two lines, and automatically paginated every 2.6 seconds.
Call `messages.dismiss()` when the notification is acknowledged.
