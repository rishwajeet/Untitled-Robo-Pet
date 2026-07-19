#pragma once

#include <Adafruit_SSD1306.h>

#include "../../assets/faces/generated/pet_animations.h"

class PetFaceAnimator {
 public:
  explicit PetFaceAnimator(Adafruit_SSD1306& display) : display_(display) {}

  void begin(const PetAnimation& base_animation, uint32_t now_ms = 0) {
    base_animation_ = &base_animation;
    start(base_animation, false, now_ms);
  }

  void setBase(const PetAnimation& animation, uint32_t now_ms) {
    base_animation_ = &animation;
    start(animation, false, now_ms);
  }

  void play(const PetAnimation& animation, bool restore_base, uint32_t now_ms) {
    start(animation, restore_base, now_ms);
  }

  void update(uint32_t now_ms) {
    if (animation_ == nullptr || frame_rendered_ == false) {
      renderCurrentFrame();
      frame_started_ms_ = now_ms;
      frame_rendered_ = true;
      return;
    }

    const PetAnimationFrame& frame = animation_->frames[frame_index_];
    if (now_ms - frame_started_ms_ < frame.duration_ms) return;

    if (frame_index_ + 1 < animation_->frame_count) {
      frame_index_++;
    } else if (animation_->loop) {
      frame_index_ = 0;
    } else if (restore_base_ && base_animation_ != nullptr) {
      start(*base_animation_, false, now_ms);
      renderCurrentFrame();
      frame_rendered_ = true;
      return;
    } else {
      return;
    }

    renderCurrentFrame();
    frame_started_ms_ = now_ms;
  }

 private:
  void start(const PetAnimation& animation, bool restore_base, uint32_t now_ms) {
    animation_ = &animation;
    restore_base_ = restore_base;
    frame_index_ = 0;
    frame_started_ms_ = now_ms;
    frame_rendered_ = false;
  }

  void renderCurrentFrame() {
    if (animation_ == nullptr) return;
    display_.clearDisplay();
    display_.drawBitmap(
        0, 0, animation_->frames[frame_index_].bitmap, 128, 32, SSD1306_WHITE);
    display_.display();
  }

  Adafruit_SSD1306& display_;
  const PetAnimation* animation_ = nullptr;
  const PetAnimation* base_animation_ = nullptr;
  uint32_t frame_started_ms_ = 0;
  uint8_t frame_index_ = 0;
  bool restore_base_ = false;
  bool frame_rendered_ = false;
};
