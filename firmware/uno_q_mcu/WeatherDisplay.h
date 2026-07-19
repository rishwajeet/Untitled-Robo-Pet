#pragma once

#include <Adafruit_SSD1306.h>
#include <stdio.h>
#include <string.h>

#include "../../assets/weather/generated/weather_icons.h"

struct WeatherReading {
  int16_t temperature_tenths_c;
  uint8_t precipitation_percent;
  const char* label;
};

class WeatherDisplay {
 public:
  explicit WeatherDisplay(Adafruit_SSD1306& display) : display_(display) {}

  void show(const WeatherIconAnimation& icon,
            const WeatherReading& reading,
            uint32_t now_ms) {
    icon_ = &icon;
    reading_ = reading;
    frame_index_ = 0;
    frame_started_ms_ = now_ms;
    render();
  }

  void update(uint32_t now_ms) {
    if (icon_ == nullptr) return;
    const WeatherIconFrame& frame = icon_->frames[frame_index_];
    if (now_ms - frame_started_ms_ < frame.duration_ms) return;
    frame_index_ = (frame_index_ + 1) % icon_->frame_count;
    frame_started_ms_ = now_ms;
    render();
  }

 private:
  void renderTemperature() {
    const int16_t whole = reading_.temperature_tenths_c / 10;
    char temperature[7];
    snprintf(temperature, sizeof(temperature), "%d", whole);
    display_.setTextSize(2);
    display_.setTextColor(SSD1306_WHITE);
    display_.setCursor(43, 2);
    display_.print(temperature);

    // Adafruit's built-in font has no dependable degree glyph, so draw it.
    const int16_t degree_x = 43 + strlen(temperature) * 12;
    display_.drawCircle(degree_x + 2, 4, 2, SSD1306_WHITE);
    display_.setTextSize(1);
    display_.setCursor(degree_x + 7, 3);
    display_.print('C');
  }

  void render() {
    display_.clearDisplay();
    display_.drawBitmap(0, 0, icon_->frames[frame_index_].bitmap,
                        WEATHER_ICON_WIDTH, WEATHER_ICON_HEIGHT, SSD1306_WHITE);
    renderTemperature();

    display_.setTextSize(1);
    display_.setTextColor(SSD1306_WHITE);
    display_.setCursor(98, 3);
    display_.print('R');
    display_.print(reading_.precipitation_percent);
    display_.print('%');

    display_.setCursor(43, 23);
    for (uint8_t index = 0; index < 14 && reading_.label[index] != '\0'; index++) {
      display_.print(reading_.label[index]);
    }
    display_.display();
  }

  Adafruit_SSD1306& display_;
  const WeatherIconAnimation* icon_ = nullptr;
  WeatherReading reading_{0, 0, ""};
  uint32_t frame_started_ms_ = 0;
  uint8_t frame_index_ = 0;
};
