#pragma once

#include <Adafruit_SSD1306.h>
#include <stdio.h>
#include <string.h>

class MessageDisplay {
 public:
  explicit MessageDisplay(Adafruit_SSD1306& display) : display_(display) {}

  void show(const char* sender, const char* message, uint32_t now_ms) {
    copyClean(sender_, sizeof(sender_), sender);
    copyClean(message_, sizeof(message_), message);
    buildPages();
    page_index_ = 0;
    shown_at_ms_ = now_ms;
    page_started_ms_ = now_ms;
    visible_ = true;
    render(now_ms);
  }

  void update(uint32_t now_ms) {
    if (!visible_) return;

    // Redraw the icon during the short arrival pulse.
    if (now_ms - shown_at_ms_ < kArrivalDurationMs) {
      render(now_ms);
    }

    if (page_count_ > 1 && now_ms - page_started_ms_ >= kPageDurationMs) {
      page_index_ = (page_index_ + 1) % page_count_;
      page_started_ms_ = now_ms;
      render(now_ms);
    }
  }

  void dismiss() {
    visible_ = false;
    display_.clearDisplay();
    display_.display();
  }

  bool visible() const { return visible_; }
  uint8_t page() const { return page_index_ + 1; }
  uint8_t pageCount() const { return page_count_; }

 private:
  static constexpr uint8_t kColumns = 21;
  static constexpr uint8_t kMaxPages = 8;
  static constexpr uint32_t kPageDurationMs = 2600;
  static constexpr uint32_t kArrivalDurationMs = 480;

  static void copyClean(char* destination, size_t size, const char* source) {
    if (size == 0) return;
    size_t out = 0;
    bool previous_space = true;
    for (size_t index = 0; source && source[index] && out + 1 < size; index++) {
      unsigned char value = static_cast<unsigned char>(source[index]);
      const bool is_space = value <= 32 || value == 127;
      if (is_space) {
        if (!previous_space) destination[out++] = ' ';
        previous_space = true;
      } else {
        destination[out++] = value < 128 ? static_cast<char>(value) : '?';
        previous_space = false;
      }
    }
    if (out > 0 && destination[out - 1] == ' ') out--;
    destination[out] = '\0';
  }

  uint16_t nextLine(uint16_t start) const {
    const uint16_t length = strlen(message_);
    while (start < length && message_[start] == ' ') start++;
    if (start >= length) return length;

    uint16_t end = start + kColumns;
    if (end >= length) return length;
    if (message_[end] == ' ') {
      while (end < length && message_[end] == ' ') end++;
      return end;
    }

    uint16_t break_at = end;
    while (break_at > start && message_[break_at] != ' ') break_at--;
    if (break_at == start) return end;  // one word longer than the display
    while (break_at < length && message_[break_at] == ' ') break_at++;
    return break_at;
  }

  void buildPages() {
    page_count_ = 0;
    uint16_t position = 0;
    const uint16_t length = strlen(message_);
    do {
      page_starts_[page_count_++] = position;
      position = nextLine(position);
      position = nextLine(position);
    } while (position < length && page_count_ < kMaxPages);
  }

  uint16_t drawLine(uint16_t start, int16_t y) {
    const uint16_t length = strlen(message_);
    while (start < length && message_[start] == ' ') start++;
    uint16_t next = nextLine(start);
    uint16_t end = next;
    while (end > start && message_[end - 1] == ' ') end--;
    if (end - start > kColumns) end = start + kColumns;

    display_.setCursor(0, y);
    for (uint16_t index = start; index < end; index++) {
      display_.print(message_[index]);
    }
    return next;
  }

  void drawChatIcon(bool filled) {
    if (filled) {
      display_.fillRoundRect(0, 0, 11, 8, 2, SSD1306_WHITE);
      display_.fillTriangle(2, 7, 2, 10, 5, 7, SSD1306_WHITE);
    } else {
      display_.drawRoundRect(0, 0, 11, 8, 2, SSD1306_WHITE);
      display_.drawLine(2, 7, 2, 10, SSD1306_WHITE);
      display_.drawLine(2, 10, 5, 7, SSD1306_WHITE);
    }
  }

  void render(uint32_t now_ms) {
    display_.clearDisplay();
    display_.setTextColor(SSD1306_WHITE);
    display_.setTextSize(1);

    const uint32_t arrival_age = now_ms - shown_at_ms_;
    const bool pulse = arrival_age < kArrivalDurationMs && (arrival_age / 120) % 2 == 0;
    drawChatIcon(pulse);

    display_.setCursor(14, 1);
    for (uint8_t index = 0; index < 14 && sender_[index]; index++) {
      display_.print(sender_[index]);
    }

    if (page_count_ > 1) {
      char counter[6];
      snprintf(counter, sizeof(counter), "%u/%u", page_index_ + 1, page_count_);
      display_.setCursor(128 - strlen(counter) * 6, 1);
      display_.print(counter);
    }

    display_.drawLine(0, 11, 127, 11, SSD1306_WHITE);
    uint16_t position = page_starts_[page_index_];
    position = drawLine(position, 13);
    drawLine(position, 23);
    display_.display();
  }

  Adafruit_SSD1306& display_;
  char sender_[32]{};
  char message_[256]{};
  uint16_t page_starts_[kMaxPages]{};
  uint32_t shown_at_ms_ = 0;
  uint32_t page_started_ms_ = 0;
  uint8_t page_index_ = 0;
  uint8_t page_count_ = 1;
  bool visible_ = false;
};
