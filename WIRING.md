# WIRING SHEET — read this whole page before touching a wire

**The board runs 3.3V logic. Everything wires to 3.3V. Never the 5V pin.**
(5V pin is a power rail only. Also: any header tied to the Linux processor
is 1.8V and can be damaged by 3.3V — don't freelance-wire unlabeled pins.)

**GOLDEN RULE: wire first, reset after.** The sketch detects the OLED and
Modulino ONCE at boot and permanently skips missing hardware. After any
wiring change: press reset once (or re-plug power). A dead screen after
hot-wiring is not a bug — it needs the reset.

## Pin map

| Part | Hookup |
|---|---|
| OLED 0.91" (SSD1306) | VCC→**3.3V**, GND→GND, SDA→**the pin labeled SDA**, SCL→**the pin labeled SCL** (top of the digital header, next to AREF). **NOT A4/A5** — on the UNO Q those are plain analog pins, unlike a classic Uno. (I2C 0x3C) |
| Modulino Movement | Qwiic cable → Qwiic port. That's it. |
| Speaker | **D9** → pot outer leg; pot **middle leg (wiper)** → speaker+; speaker− → GND. Pot = volume knob AND protects the pin. Never bypass the pot. |
| Talk button | **D2** → one leg; other leg → GND |
| Pet button | **D3** → one leg; other leg → GND |
| Red LEDs | **D5**, **D6** → long leg; short leg → GND (through 220Ω if we got any) |
| Blue LEDs | **D10**, **D11** → same pattern |
| LDR | ONLY if we have a spare ~10K resistor: 3.3V→LDR→**A0**, and A0→10K→GND. **If NOT wiring the LDR: jumper A0 → 3.3V** (a floating A0 fires random sleep/wake events). |

Buttons use internal pull-ups — no resistors needed. If a button acts
"always pressed," its legs are rotated 90° (tactile-switch classic): turn it.

## What you should see after wiring + reset

1. Within seconds: **"BITTU"** on the OLED, then an idle face that **blinks
   every 2–5s**, blue LEDs breathing softly. Blink + breathing = body works.
2. **Shake** the board/Modulino → X-eyes + falling beep.
   **Lift** it → surprised face + chirp. **Tap** it → happy face.
   (Thresholds are untuned first-guesses — report if jumpy or numb, tuning
   is a 1-minute reflash.)
3. **D2 button** → curious face + beep. **D3 button** → love face + beep.
4. Beeps are **quiet** (bare speaker, no amp). Silent? Rotate the pot first,
   then check wiring.
5. LED never lights → it's backwards (long leg goes to the pin side).

## Serial test (proves the whole protocol, no Linux code needed)

On the Mac with the board on USB:

```bash
arduino-cli board list          # find the fresh /dev/cu.usbmodemXXXX (number changes per plug-in!)
arduino-cli monitor -p /dev/cu.usbmodemXXXX --config 115200
```

- Press a button → you should see `{"e":"talk"}` / `{"e":"pet"}`.
- Shake it → `{"e":"shake"}`.
- Type `{"c":"face","v":"claude_done"}` + Enter → Claude-done face on OLED.
- Type `{"c":"mood","v":"angry"}` → angry face. `{"c":"beep","v":"happy"}` → chirp.

If events print and commands change the face: **the entire serial protocol
is proven** and the Linux brain bolts straight on.

If NOTHING prints on button press: the MCU's Serial may route to the Q's
internal Linux bridge instead of the USB port. That's not a failure — tell
Claude (orchestrator session), it changes one config line in transport.py.
