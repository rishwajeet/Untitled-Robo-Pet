#!/bin/bash
# Physical approval: Claude Code wants to run a Bash command -> the ROBOT asks.
# Talk button = allow, pet button = deny. The demo beat that wins the room.
# Set ROBOT_IP, chmod +x this file, wire it as a PreToolUse hook (Bash matcher).
ROBOT="${ROBOT_IP:-ROBOT}:8300"

curl -s -m 2 -X POST "http://$ROBOT/ask" -d '{"text":"ALLOW claude cmd?"}' >/dev/null

for _ in $(seq 1 40); do  # poll up to 20s
  ANS=$(curl -s -m 2 "http://$ROBOT/answer" | grep -o '"answer": *"[a-z]*"' | grep -o '[a-z]*"$' | tr -d '"')
  if [ "$ANS" = "yes" ]; then exit 0; fi
  if [ "$ANS" = "no" ]; then echo "Bittu denied this command." >&2; exit 2; fi
  sleep 0.5
done
exit 0  # timeout -> allow, so a dead robot never bricks the demo laptop
