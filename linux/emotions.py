"""Small, deterministic social/display state machines for Bittu."""
from dataclasses import dataclass


@dataclass
class PresenceTracker:
    """Turn noisy face counts into meaningful social transitions."""

    arrive_after: float = 0.8
    leave_after: float = 12.0
    join_after: float = 0.8
    present: bool = False
    count: int = 0
    _face_since: float | None = None
    _last_face_at: float | None = None
    _candidate_count: int = 0
    _candidate_since: float | None = None

    def update(self, detected: int, now: float) -> str | None:
        detected = max(0, detected)
        if detected:
            self._last_face_at = now
            if not self.present:
                if self._face_since is None:
                    self._face_since = now
                if now - self._face_since >= self.arrive_after:
                    self.present = True
                    self.count = detected
                    self._candidate_count = detected
                    self._candidate_since = None
                    return "arrived"
                return None

            if detected > self.count:
                if detected != self._candidate_count:
                    self._candidate_count = detected
                    self._candidate_since = now
                elif now - self._candidate_since + 1e-9 >= self.join_after:
                    self.count = detected
                    self._candidate_since = None
                    return "joined"
            else:
                self._candidate_count = detected
                self._candidate_since = None
            return None

        self._face_since = None
        self._candidate_since = None
        if self.present and self._last_face_at is not None and \
                now - self._last_face_at >= self.leave_after:
            self.present = False
            self.count = 0
            return "left"
        return None


class EmotionDirector:
    """High-level API for layered base, reaction, and activity state."""

    def __init__(self, link):
        self.link = link
        self.base_mood = "idle"

    def base(self, mood: str):
        if mood != self.base_mood:
            self.base_mood = mood
            self.link.send("base", mood)

    def react(self, mood: str):
        self.link.send("react", mood)

    def activity(self, name: str | None):
        self.link.send("activity", name or "clear")

    def caption(self, text: str):
        self.link.text(text)
