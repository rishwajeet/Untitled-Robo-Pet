#!/bin/bash
# Supervisor: Bittu must not stay dead. Any crash -> log it, restart in 2s.
# Usage: source your env first, then ./run_bittu.sh
cd "$(dirname "$0")"
while true; do
  echo "[supervisor] starting brain $(date +%H:%M:%S)"
  /Users/rishwajeetsingh/Documents/machine_house/.venv/bin/python -u brain.py
  echo "[supervisor] brain exited ($?) — restarting in 2s"
  sleep 2
done
