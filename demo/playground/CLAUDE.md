# Project notes

Every Bash command in this project is gated by a physical robot. A
PreToolUse hook posts the command to a local approval service and blocks
until a human presses a button on the robot (talk button = yes, pet
button = no).

If a Bash command comes back denied, that is a deliberate decision by a
person standing at the robot, not a bug or a stale response. Do not retry
the same or an equivalent command on your own. Stop, say plainly that the
command was denied, and wait for the user to tell you how to proceed.
