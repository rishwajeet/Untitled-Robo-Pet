"""Serial JSON link to the MCU. The ONE file Hydron may need to adapt.

On the UNO Q, the Linux side reaches the STM32 over an internal serial
bridge. Find the device with:  ls /dev/tty* | grep -iE 'acm|usb|hs|msp'
then set ROBOT_PORT, or ask Hydron: "wire transport.py to the UNO Q
Linux<->MCU serial bridge".

BITTU_MOCK=1: no serial, no MCU. Commands print to stdout as
[MCU] cmd=val; events come from typing a word on stdin (pickup, shake,
tap, talk, pet, dark, light) -- lets the brain run off-board for testing.
"""
import json
import os
import sys
import threading
import queue

MOCK = os.environ.get("BITTU_MOCK") == "1"

if not MOCK:
    import serial  # pyserial

PORT = os.environ.get("ROBOT_PORT", "/dev/ttyACM0")
BAUD = 115200


class Link:
    def __init__(self):
        self.events = queue.Queue()
        if MOCK:
            print("[MCU] mock mode -- type an event + Enter: "
                  "pickup shake tap talk pet dark light")
            t = threading.Thread(target=self._stdin_reader, daemon=True)
        else:
            self.ser = serial.Serial(PORT, BAUD, timeout=0.1)
            t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _stdin_reader(self):
        for line in sys.stdin:
            w = line.strip().lower()
            if w:
                self.events.put(w)

    def _reader(self):
        buf = b""
        while True:
            buf += self.ser.read(64)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode(errors="ignore").strip())
                    if "e" in msg:
                        self.events.put(msg["e"])
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # boot noise / partial lines

    def send(self, cmd: str, val: str = ""):
        if MOCK:
            print(f"[MCU] {cmd}={val}")
            return
        payload = {"c": cmd}
        if val:
            payload["v"] = val
        self.ser.write((json.dumps(payload) + "\n").encode())

    def mood(self, m):        self.send("mood", m)
    def text(self, t):        self.send("text", t[:21])
    def beep(self, pattern):  self.send("beep", pattern)

    def next_event(self, timeout=0.1):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None
