#!/bin/bash
# deploy_to_board.sh -- migrate the brain from the Mac back onto the UNO Q's
# own Linux side, whenever there's time to do it properly.
#
# NOT the active path today: the brain runs ON THE MAC, tethered to the
# board over USB serial (see README STATUS). This script is what "migrate
# later" means, staged and ready but not run yet. The linux/ code itself
# needs zero changes to make this switch -- transport.py already supports
# the board's internal serial bridge (ROBOT_PORT) same as it always did;
# this script is just the mechanics of getting it there and installed.
#
# Usage:  ./deploy_to_board.sh
#   Requires the board to be adb-reachable (`adb devices` shows exactly one
#   device) AND idle -- do NOT run this while Hydron is mid-flash on the MCU
#   side. Read-only recon (adb devices, adb shell uptime) is always safe;
#   this script's push/install steps are not, so it bails if the device
#   isn't there or is ambiguous.
#
# What it does:
#   1. Confirms adb sees exactly one device.
#   2. adb shell uptime -- confirms shell access without touching anything.
#   3. Pushes linux/'s contents to a directory on the board.
#   4. Creates a venv there and installs requirements.txt (already pinned to
#      the exact opencv/numpy combo that has a working CascadeClassifier --
#      see requirements.txt's own comments for why that pin exists).
#   5. Dry-run imports brain.py to catch aarch64-specific import errors
#      early, before anyone's standing at the desk waiting on it.
#
# Does NOT start brain.py automatically. That's deliberate: a human should
# confirm the board is actually ready (MCU flashed, wiring done, camera
# plugged in, ROBOT_PORT known) before the main loop goes live.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LINUX_DIR="$REPO_ROOT/linux"
BOARD_DIR="/home/arduino/bittu"   # placeholder -- adjusted below once we know

echo "=== checking adb device ==="
DEVICE_COUNT=$(adb devices | grep -c "device$" || true)
if [ "$DEVICE_COUNT" -eq 0 ]; then
    echo "No adb device found. Plug in the board and make sure it's NOT"
    echo "mid-flash (check with whoever's running Hydron) before retrying."
    exit 1
fi
if [ "$DEVICE_COUNT" -gt 1 ]; then
    echo "Multiple adb devices found -- rerun adb commands with -s <serial>."
    adb devices
    exit 1
fi

echo "=== confirming shell access (read-only, safe even mid-flash) ==="
adb shell uptime

echo "=== board user + adjusting deploy dir ==="
BOARD_USER=$(adb shell whoami | tr -d '\r\n')
echo "board user: $BOARD_USER"
if [ "$BOARD_USER" != "arduino" ]; then
    BOARD_DIR="/home/$BOARD_USER/bittu"
fi
echo "deploying to: $BOARD_DIR"

echo "=== pushing linux/ contents to $BOARD_DIR ==="
adb shell "mkdir -p $BOARD_DIR"
adb push "$LINUX_DIR/." "$BOARD_DIR/"

echo "=== board python version ==="
adb shell "python3 --version"

echo "=== venv + pip install (uses the pinned requirements.txt as-is) ==="
adb shell "cd $BOARD_DIR && python3 -m venv .venv && \
    .venv/bin/pip install --upgrade pip && \
    .venv/bin/pip install -r requirements.txt"

echo "=== dry-run import check ==="
if ! adb shell "cd $BOARD_DIR && .venv/bin/python3 -c 'import brain'"; then
    echo "import brain failed. If it's opencv/numpy specifically, the pip"
    echo "wheel may not have a prebuilt aarch64 binary for this Python --"
    echo "fall back to: adb shell 'sudo apt-get install -y python3-opencv'"
    echo "and recreate the venv with --system-site-packages so it picks up"
    echo "the apt-installed cv2 instead of trying to build/pip-install it."
    exit 1
fi

echo ""
echo "=== deploy done. To run the brain for real on the board: ==="
echo "  adb shell"
echo "  cd $BOARD_DIR"
echo "  export OPENAI_API_KEY=sk-..."
echo "  export ROBOT_PORT=/dev/ttyACM0   # or whatever: ls /dev/tty* | grep -iE 'acm|usb|hs|msp'"
echo "  export AUDIO_OUT=beeps           # or c6 / bt"
echo "  .venv/bin/python3 brain.py"
echo ""
echo "If ROBOT_PORT turns out not to reach the MCU from the board's own"
echo "Linux side (the internal-routing problem, not the Mac-tethered one),"
echo "run serial_relay.py on the board instead and point a Mac-side brain.py"
echo "at it with BITTU_TCP -- see serial_relay.py's own header for the"
echo "one-liner."
