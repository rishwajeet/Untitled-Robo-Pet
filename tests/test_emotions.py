import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "linux"))
from emotions import EmotionDirector, PresenceTracker  # noqa: E402


class PresenceTrackerTests(unittest.TestCase):
    def test_arrival_requires_stable_detection(self):
        tracker = PresenceTracker(arrive_after=0.8)
        self.assertIsNone(tracker.update(1, 0.0))
        self.assertIsNone(tracker.update(0, 0.4))
        self.assertIsNone(tracker.update(1, 0.5))
        self.assertEqual(tracker.update(1, 1.3), "arrived")

    def test_short_detection_gap_does_not_create_departure_or_rearrival(self):
        tracker = PresenceTracker(arrive_after=0, leave_after=12)
        self.assertEqual(tracker.update(1, 0), "arrived")
        self.assertIsNone(tracker.update(0, 5))
        self.assertIsNone(tracker.update(1, 6))
        self.assertTrue(tracker.present)

    def test_departure_requires_long_absence(self):
        tracker = PresenceTracker(arrive_after=0, leave_after=12)
        tracker.update(1, 0)
        self.assertIsNone(tracker.update(0, 11.9))
        self.assertEqual(tracker.update(0, 12), "left")

    def test_join_requires_stable_higher_count(self):
        tracker = PresenceTracker(arrive_after=0, join_after=0.8)
        tracker.update(1, 0)
        self.assertIsNone(tracker.update(2, 1))
        self.assertIsNone(tracker.update(1, 1.4))
        self.assertIsNone(tracker.update(2, 2))
        self.assertEqual(tracker.update(2, 2.8), "joined")


class FakeLink:
    def __init__(self):
        self.commands = []

    def send(self, command, value):
        self.commands.append((command, value))

    def text(self, value):
        self.commands.append(("text", value))


class EmotionDirectorTests(unittest.TestCase):
    def test_base_is_deduplicated_and_reactions_are_one_shots(self):
        link = FakeLink()
        display = EmotionDirector(link)
        display.base("idle")
        display.base("attentive")
        display.base("attentive")
        display.react("happy")
        self.assertEqual(link.commands, [
            ("base", "attentive"), ("react", "happy")])


if __name__ == "__main__":
    unittest.main()
