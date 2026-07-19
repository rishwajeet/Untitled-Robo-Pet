"""Test suite for Bittu's RPS engine. Stdlib only (unittest) — run via
run_tests.py or `python3 -m unittest test_game -v`."""
import unittest

from game import Score, decide_winner, robot_move


class TestRobotMove(unittest.TestCase):
    def test_cycles_through_all_three_moves(self):
        seen = {robot_move(i) for i in range(3)}
        self.assertEqual(seen, {"rock", "paper", "scissors"})

    def test_is_deterministic(self):
        self.assertEqual(robot_move(0), robot_move(3))
        self.assertEqual(robot_move(1), robot_move(4))


class TestDecideWinner(unittest.TestCase):
    def test_tie(self):
        self.assertEqual(decide_winner("rock", "rock"), "tie")

    def test_rock_beats_scissors(self):
        self.assertEqual(decide_winner("rock", "scissors"), "player")

    def test_scissors_beats_paper(self):
        self.assertEqual(decide_winner("scissors", "paper"), "player")

    def test_paper_beats_rock(self):
        self.assertEqual(decide_winner("rock", "paper"), "robot")


class TestScore(unittest.TestCase):
    def test_records_a_win(self):
        s = Score()
        s.record("player")
        self.assertEqual(s.wins["player"], 1)

    def test_tracks_leader(self):
        s = Score()
        s.record("player")
        s.record("player")
        s.record("robot")
        self.assertEqual(s.leader(), "player")

    def test_scoreboard_format(self):
        s = Score()
        s.record("player")
        s.record("player")
        s.record("robot")
        self.assertEqual(s.scoreboard(), "YOU 2 - 1 BITTU")


if __name__ == "__main__":
    unittest.main()
