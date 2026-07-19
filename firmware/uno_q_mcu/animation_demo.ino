#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Wire.h>

#include "PetFaceAnimator.h"

constexpr uint8_t kScreenWidth = 128;
constexpr uint8_t kScreenHeight = 32;
constexpr uint8_t kOledAddress = 0x3C;

Adafruit_SSD1306 display(kScreenWidth, kScreenHeight, &Wire, -1);
PetFaceAnimator face(display);

void setup() {
  Wire.begin();
  if (!display.begin(SSD1306_SWITCHCAPVCC, kOledAddress)) {
    while (true) delay(1000);
  }

  face.begin(PET_ANIMATION_IDLE_BLINK, millis());
}

void loop() {
  const uint32_t now = millis();
  face.update(now);

  // Replace these timed transitions with Arduino Bridge commands later.
  const uint8_t phase = (now / 5000) % 4;
  static uint8_t previous_phase = 255;
  if (phase == previous_phase) return;
  previous_phase = phase;

  if (phase == 0) face.setBase(PET_ANIMATION_IDLE_BLINK, now);
  if (phase == 1) face.setBase(PET_ANIMATION_WORKING_SCAN, now);
  if (phase == 2) face.play(PET_ANIMATION_CLAUDE_DONE, true, now);
  if (phase == 3) face.setBase(PET_ANIMATION_CLAUDE_TOOL_RUNNING, now);
}
