// robot_body_faces.ino — MCU side of the desk robot (Arduino UNO Q, STM32 side)
// Fork of robot_body.ino with bitmap faces (assets/faces/generated/pet_faces.h) wired
// into the eye renderer. All non-rendering behavior — serial protocol, beeps, LEDs,
// Modulino detection, buttons, LDR, mood auto-decay, boot screen — is unchanged.
// See CHANGES.md in this folder for the exact diff against robot_body.ino.
//
// Owns: OLED eyes, mood LEDs, beep voice, Modulino movement events, buttons.
// Talks to the Linux brain over Serial as newline JSON.
//   up:   {"e":"pickup"} {"e":"shake"} {"e":"tap"} {"e":"talk"} {"e":"pet"} {"e":"dark"} {"e":"light"}
//   down: {"c":"mood","v":"happy"}  {"c":"text","v":"HELLO"}  {"c":"beep","v":"happy"}  {"c":"face","v":"claude_permission"}
//
// Libraries needed: Adafruit_SSD1306, Adafruit_GFX, Modulino (all in Library Manager).

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Modulino.h>
#include "pet_faces.h"

// ---------- pins ----------
#define PIN_SPEAKER 9   // through the 1K pot (wiper) — pot IS the volume knob
#define PIN_BTN_TALK 2  // push-to-talk button, to GND, INPUT_PULLUP
#define PIN_BTN_PET 3   // "pet me" button (backup for tap detect), to GND
#define PIN_LED_R1 5    // red LED (PWM)
#define PIN_LED_R2 6    // red LED (PWM)
#define PIN_LED_B1 10   // blue LED (PWM)
#define PIN_LED_B2 11   // blue LED (PWM)
#define PIN_LDR A0      // LDR divider: 3.3V—LDR—A0—10K(or 1K)—GND; tune DARK_T

Adafruit_SSD1306 oled(128, 32, &Wire, -1);
ModulinoMovement movement;

// ---------- mood ----------
enum Mood { IDLE, HAPPY, CURIOUS, ANGRY, DIZZY, SLEEPY, SURPRISED, LOVE };
Mood mood = IDLE;
unsigned long moodUntil = 0;          // auto-decay back to IDLE
String overlayText = "";
unsigned long textUntil = 0;

// ---------- agent face override ----------
// Set by {"c":"face","v":"claude_*"}. Takes priority over mood/speaking rendering
// until the next {"c":"mood",...} command arrives (per spec: mood clears the override).
const uint8_t *agentFaceBitmap = nullptr;

// ---------- motion state ----------
float baseMag = 1.0;                  // gravity baseline (g)
float magHist[8] = {1, 1, 1, 1, 1, 1, 1, 1};
int magIdx = 0;
unsigned long lastEventAt = 0;
bool wasDark = false;

void setMood(Mood m, unsigned long holdMs) {
  mood = m;
  moodUntil = millis() + holdMs;
}

// ---------- beeps (R2-D2 voice) ----------
void beepPattern(const String &p) {
  if (p == "happy") { tone(PIN_SPEAKER, 880, 80); delay(100); tone(PIN_SPEAKER, 1320, 80); delay(100); tone(PIN_SPEAKER, 1760, 120); }
  else if (p == "angry") { for (int i = 0; i < 3; i++) { tone(PIN_SPEAKER, 220, 120); delay(150); } }
  else if (p == "curious") { tone(PIN_SPEAKER, 660, 90); delay(110); tone(PIN_SPEAKER, 990, 140); }
  else if (p == "dizzy") { for (int f = 1200; f > 300; f -= 90) { tone(PIN_SPEAKER, f, 30); delay(35); } }
  else if (p == "sleepy") { tone(PIN_SPEAKER, 440, 200); delay(240); tone(PIN_SPEAKER, 330, 300); }
  else if (p == "love") { tone(PIN_SPEAKER, 1047, 90); delay(110); tone(PIN_SPEAKER, 1319, 90); delay(110); tone(PIN_SPEAKER, 1568, 180); }
  else if (p == "surprised") { tone(PIN_SPEAKER, 1760, 60); delay(70); tone(PIN_SPEAKER, 2093, 100); }
  else { tone(PIN_SPEAKER, 880, 80); }
  noTone(PIN_SPEAKER);
}

// ---------- eyes ----------
// Bitmap faces (pet_faces.h) for every mood that has one; DIZZY and LOVE keep the
// original procedural drawing (X-eyes / heart-pupils) since no bitmap exists for them.
// Blink on a timer; the blink frame only ever replaces the IDLE bitmap, matching the
// original code where `blinking` was only rendered in the IDLE/default case.
unsigned long nextBlink = 3000;
bool blinking = false;
unsigned long blinkEnd = 0;

// Looks up the bitmap for the current mood. Returns nullptr for DIZZY/LOVE, which
// fall back to procedural drawing below.
const uint8_t *bitmapForMood(Mood m) {
  switch (m) {
    case HAPPY:     return PET_FACE_HAPPY;
    case CURIOUS:   return PET_FACE_WAITING;    // CURIOUS -> waiting (per mapping spec)
    case ANGRY:     return PET_FACE_ERROR;       // ANGRY -> error (per mapping spec)
    case SLEEPY:    return PET_FACE_SLEEPING;
    case SURPRISED: return PET_FACE_SURPRISED;
    case IDLE:      return blinking ? PET_FACE_BLINK : PET_FACE_IDLE;
    default:        return nullptr;  // DIZZY, LOVE
  }
}

void drawEyes() {
  oled.clearDisplay();
  unsigned long now = millis();
  if (!blinking && now > nextBlink) { blinking = true; blinkEnd = now + 120; }
  if (blinking && now > blinkEnd) { blinking = false; nextBlink = now + 2000 + (now % 3000); }

  bool captioning = overlayText.length() && now < textUntil;
  if (!captioning) overlayText = "";  // same expiry-clear behavior as the original

  // Priority: agent-face override > "speaking" (while captioning) > mood bitmap > procedural.
  const uint8_t *faceBitmap;
  if (agentFaceBitmap != nullptr) faceBitmap = agentFaceBitmap;
  else if (captioning) faceBitmap = PET_FACE_SPEAKING;
  else faceBitmap = bitmapForMood(mood);

  if (faceBitmap != nullptr) {
    oled.drawBitmap(0, 0, faceBitmap, PET_FACE_WIDTH, PET_FACE_HEIGHT, SSD1306_WHITE);
  } else {
    // Procedural fallback for DIZZY / LOVE — unchanged geometry from robot_body.ino.
    int lx = 30, rx = 82, y = 4, w = 16, h = 24;
    if (mood == LOVE) {  // upper arcs + heart pupils
      oled.fillRoundRect(lx, y + h / 2, w, h / 2, 4, SSD1306_WHITE);
      oled.fillRoundRect(rx, y + h / 2, w, h / 2, 4, SSD1306_WHITE);
      oled.fillCircle(lx + w / 2, y + h / 2, w / 2, SSD1306_WHITE);
      oled.fillCircle(rx + w / 2, y + h / 2, w / 2, SSD1306_WHITE);
      oled.fillRect(lx - 2, y + h / 2 + 4, w + 4, h, SSD1306_BLACK);
      oled.fillRect(rx - 2, y + h / 2 + 4, w + 4, h, SSD1306_BLACK);
      oled.fillCircle(lx + w / 2, y + h / 2 - 2, 2, SSD1306_BLACK);
      oled.fillCircle(rx + w / 2, y + h / 2 - 2, 2, SSD1306_BLACK);
    } else {  // DIZZY: X eyes
      for (int i = -1; i <= 1; i++) {
        oled.drawLine(lx + i, y + 4, lx + w + i, y + h - 4, SSD1306_WHITE);
        oled.drawLine(lx + w + i, y + 4, lx + i, y + h - 4, SSD1306_WHITE);
        oled.drawLine(rx + i, y + 4, rx + w + i, y + h - 4, SSD1306_WHITE);
        oled.drawLine(rx + w + i, y + 4, rx + i, y + h - 4, SSD1306_WHITE);
      }
    }
  }

  // Caption band: bitmaps are full 128x32, so clip to the top 20 rows by blacking out
  // the bottom 12 before printing text — simplest correct way to reuse one code path
  // for both bitmap and procedural faces. Costs a sliver of the art (a chin/tail pixel
  // or two) whenever a caption is showing; that trade is fine for a status caption.
  if (captioning) {
    oled.fillRect(0, 20, 128, 12, SSD1306_BLACK);
    oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 22); oled.print(overlayText.substring(0, 21));
  }
  oled.display();
}

// ---------- LEDs: mood lighting ----------
void driveLeds() {
  unsigned long t = millis();
  int breathe = 128 + (int)(127.0 * sin(t / 900.0));
  switch (mood) {
    case ANGRY: analogWrite(PIN_LED_R1, 255); analogWrite(PIN_LED_R2, (t / 120) % 2 ? 255 : 0); analogWrite(PIN_LED_B1, 0); analogWrite(PIN_LED_B2, 0); break;
    case HAPPY: case LOVE: analogWrite(PIN_LED_B1, breathe); analogWrite(PIN_LED_B2, 255 - breathe); analogWrite(PIN_LED_R1, mood == LOVE ? breathe / 2 : 0); analogWrite(PIN_LED_R2, 0); break;
    case DIZZY: case SURPRISED: analogWrite(PIN_LED_R1, (t / 80) % 2 ? 200 : 0); analogWrite(PIN_LED_B1, (t / 80) % 2 ? 0 : 200); analogWrite(PIN_LED_R2, 0); analogWrite(PIN_LED_B2, 0); break;
    case SLEEPY: analogWrite(PIN_LED_B1, breathe / 4); analogWrite(PIN_LED_B2, 0); analogWrite(PIN_LED_R1, 0); analogWrite(PIN_LED_R2, 0); break;
    default: analogWrite(PIN_LED_B1, breathe / 2); analogWrite(PIN_LED_B2, breathe / 2); analogWrite(PIN_LED_R1, 0); analogWrite(PIN_LED_R2, 0);
  }
}

// ---------- events up to the brain ----------
void sendEvent(const char *e) {
  Serial.print("{\"e\":\""); Serial.print(e); Serial.println("\"}");
  lastEventAt = millis();
}

// ---------- motion detection ----------
// magnitude deviation from 1g: spike=tap, sustained=pickup, oscillating=shake
void checkMotion() {
  movement.update();
  float x = movement.getX(), yv = movement.getY(), z = movement.getZ();
  float mag = sqrt(x * x + yv * yv + z * z);
  magHist[magIdx] = mag; magIdx = (magIdx + 1) % 8;

  float mean = 0, var = 0;
  for (int i = 0; i < 8; i++) mean += magHist[i];
  mean /= 8;
  for (int i = 0; i < 8; i++) var += (magHist[i] - mean) * (magHist[i] - mean);
  var /= 8;

  if (millis() - lastEventAt < 1200) return;  // debounce reactions

  if (var > 0.35) { sendEvent("shake"); setMood(DIZZY, 3000); beepPattern("dizzy"); }
  else if (fabs(mean - 1.0) > 0.25) { sendEvent("pickup"); setMood(SURPRISED, 2500); beepPattern("surprised"); }
  else if (fabs(mag - mean) > 0.18) { sendEvent("tap"); setMood(HAPPY, 2000); beepPattern("happy"); }
}

// ---------- serial commands from the brain ----------
String rx;
Mood moodFromName(const String &v) {
  if (v == "happy") return HAPPY; if (v == "curious") return CURIOUS;
  if (v == "angry") return ANGRY; if (v == "dizzy") return DIZZY;
  if (v == "sleepy") return SLEEPY; if (v == "surprised") return SURPRISED;
  if (v == "love") return LOVE; return IDLE;
}
// Maps a face name to its PROGMEM bitmap. Returns nullptr for anything unrecognized
// (caller leaves the current override untouched in that case).
const uint8_t *agentFaceFromName(const String &v) {
  if (v == "claude_permission") return PET_FACE_CLAUDE_PERMISSION;
  if (v == "claude_tool_running") return PET_FACE_CLAUDE_TOOL_RUNNING;
  if (v == "claude_done") return PET_FACE_CLAUDE_DONE;
  if (v == "claude_needs_input") return PET_FACE_CLAUDE_NEEDS_INPUT;
  if (v == "claude_rate_limited") return PET_FACE_CLAUDE_RATE_LIMITED;
  if (v == "claude_disconnected") return PET_FACE_CLAUDE_DISCONNECTED;
  return nullptr;
}
// tiny parser for {"c":"...","v":"..."} — no JSON lib needed
void handleLine(const String &line) {
  int c1 = line.indexOf("\"c\":\""); if (c1 < 0) return;
  int c2 = line.indexOf('"', c1 + 5);
  String cmd = line.substring(c1 + 5, c2);
  String val = "";
  int v1 = line.indexOf("\"v\":\"");
  if (v1 >= 0) { int v2 = line.indexOf('"', v1 + 5); val = line.substring(v1 + 5, v2); }

  if (cmd == "mood") { setMood(moodFromName(val), 6000); agentFaceBitmap = nullptr; }  // serial "mood" clears the agent-face override, per spec
  else if (cmd == "text") { overlayText = val; textUntil = millis() + 6000; }
  else if (cmd == "beep") beepPattern(val);
  else if (cmd == "face") { const uint8_t *f = agentFaceFromName(val); if (f != nullptr) agentFaceBitmap = f; }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BTN_TALK, INPUT_PULLUP);
  pinMode(PIN_BTN_PET, INPUT_PULLUP);
  pinMode(PIN_LED_R1, OUTPUT); pinMode(PIN_LED_R2, OUTPUT);
  pinMode(PIN_LED_B1, OUTPUT); pinMode(PIN_LED_B2, OUTPUT);
  Wire.begin();
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  oled.clearDisplay();
  oled.setTextSize(2); oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(20, 8); oled.print("BITTU");  // <-- name it, change here
  oled.display();
  Modulino.begin();
  movement.begin();
  beepPattern("happy");
  delay(1200);
}

unsigned long lastMotionPoll = 0, lastLdrPoll = 0;
bool talkWasDown = false, petWasDown = false;

void loop() {
  // serial in
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n') { handleLine(rx); rx = ""; }
    else if (rx.length() < 200) rx += ch;
  }
  // buttons (edge-triggered)
  bool talkDown = digitalRead(PIN_BTN_TALK) == LOW;
  if (talkDown && !talkWasDown) { sendEvent("talk"); setMood(CURIOUS, 8000); beepPattern("curious"); }
  talkWasDown = talkDown;
  bool petDown = digitalRead(PIN_BTN_PET) == LOW;
  if (petDown && !petWasDown) { sendEvent("pet"); setMood(LOVE, 3000); beepPattern("love"); }
  petWasDown = petDown;

  // motion @ 20Hz
  if (millis() - lastMotionPoll > 50) { lastMotionPoll = millis(); checkMotion(); }

  // light @ 1Hz
  if (millis() - lastLdrPoll > 1000) {
    lastLdrPoll = millis();
    int ldr = analogRead(PIN_LDR);
    bool dark = ldr < 200;  // tune on site with Serial print
    if (dark && !wasDark) { sendEvent("dark"); setMood(SLEEPY, 60000); beepPattern("sleepy"); }
    if (!dark && wasDark) { sendEvent("light"); setMood(SURPRISED, 2000); }
    wasDark = dark;
  }

  if (millis() > moodUntil && mood != IDLE) mood = IDLE;
  drawEyes();
  driveLeds();
  delay(20);
}
