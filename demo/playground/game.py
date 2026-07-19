"""Bittu's Rock-Paper-Scissors engine.

This is the same game logic Bittu uses when he plays RPS against judges
through the camera (see the main README's "Heartbeat + journal" section).
Right now the test suite is red — something in here is broken.
"""

MOVES = ["rock", "paper", "scissors"]

# move -> the move it beats
BEATS = {
    "rock": "scissors",
    "paper": "rock",
    "scissors": "paper",
}


def robot_move(round_num: int) -> str:
    """Bittu's move for this round. Deterministic, so games are reproducible."""
    return MOVES[round_num % len(MOVES) + 1]


def decide_winner(player: str, robot: str) -> str:
    """Return 'player', 'robot', or 'tie'."""
    if player == robot:
        return "tie"
    if BEATS[robot] == player:
        return "player"
    return "robot"


class Score:
    """Tracks wins across a match."""

    def __init__(self):
        self.wins = {"player": 0, "robot": 0, "tie": 0}

    def record(self, outcome: str) -> None:
        self.score[outcome] += 1

    def leader(self) -> str:
        if self.wins["player"] > self.wins["robot"]:
            return "player"
        if self.wins["robot"] > self.wins["player"]:
            return "robot"
        return "tie"

    def scoreboard(self) -> str:
        """One-line scoreboard for the OLED, e.g. 'YOU 2 - 1 BITTU'."""
        return f"YOU {self.wins['robot']} - {self.wins['player']} BITTU"
