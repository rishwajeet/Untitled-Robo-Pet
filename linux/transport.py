"""Serial JSON link to the MCU. The ONE file Hydron may need to adapt.

Three modes, checked in this order:

1. BITTU_MOCK=1: no serial, no MCU. Commands print to stdout as
   [MCU] cmd=val; events come from typing a word on stdin (pickup, shake,
   tap, talk, pet, dark, light) -- lets the brain run off-board for testing.
2. BITTU_TCP=host:port: speaks the same newline-JSON protocol over a TCP
   socket instead of pyserial -- the contingency if the board's USB only
   exposes the Q's Linux/debug side and not a direct serial passthrough to
   the MCU. Point this at serial_relay.py running on the Q (see that file).
   Reconnects with a short backoff so a cable wobble doesn't kill the brain.
3. Real serial (default): current architecture is the brain running ON THE
   MAC, tethered to the board over USB (see README STATUS) -- the board
   enumerates as /dev/cu.usbmodemXXXX. ROBOT_PORT always wins if set;
   otherwise on macOS we autodetect the first usbmodem device. On the UNO Q
   itself the old internal-bridge path still applies: find the device with
   ls /dev/tty* | grep -iE 'acm|usb|hs|msp', then set ROBOT_PORT.
"""
import glob
import json
import os
import socket
import sys
import threading
import time
import queue

MOCK = os.environ.get("BITTU_MOCK") == "1"
TCP_ADDR = os.environ.get("BITTU_TCP", "")  # "host:port" -> serial_relay.py

if not MOCK and not TCP_ADDR:
    import serial  # pyserial

BAUD = 115200


def _resolve_port() -> str:
    """Explicit ROBOT_PORT always wins. Otherwise autodetect on macOS --
    that's the Mac-tethered path we're running today."""
    port = os.environ.get("ROBOT_PORT")
    if port:
        return port
    if sys.platform == "darwin":
        matches = sorted(glob.glob("/dev/cu.usbmodem*"))
        if matches:
            print(f"[transport] autodetected board at {matches[0]}")
            return matches[0]
        print("[transport] no /dev/cu.usbmodem* found -- "
              "falling back to /dev/ttyACM0")
    return "/dev/ttyACM0"


class Link:
    def __init__(self):
        self.events = queue.Queue()
        self._txq = queue.Queue()
        self._sock = None
        self._sock_lock = threading.Lock()
        self.observer = None
        if MOCK:
            print("[MCU] mock mode -- type an event + Enter: "
                  "pickup shake tap talk pet dark light")
            t = threading.Thread(target=self._stdin_reader, daemon=True)
        elif TCP_ADDR:
            host, _, port = TCP_ADDR.partition(":")
            self._tcp_host, self._tcp_port = host, int(port)
            print(f"[transport] TCP mode -> {host}:{port}")
            t = threading.Thread(target=self._tcp_loop, daemon=True)
        else:
            self.ser = serial.Serial(_resolve_port(), BAUD, timeout=0.1)
            t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def set_observer(self, fn):
        """Observe MCU events and outgoing commands for the dashboard."""
        self.observer = fn

    def _stdin_reader(self):
        for line in sys.stdin:
            w = line.strip().lower()
            if w:
                self.events.put(w)
                if self.observer:
                    self.observer("event", w)

    def _reopen_serial(self):
        import time as _t
        try:
            while True:
                self._txq.get_nowait()  # drop commands aimed at the dead link
        except queue.Empty:
            pass
        while True:
            try:
                self.ser = serial.Serial(_resolve_port(), BAUD, timeout=0.1)
                print("[transport] serial reconnected")
                return
            except Exception:
                _t.sleep(2)  # board unplugged/re-enumerating — keep trying

    def _reader(self):
        import time as _t
        buf = b""
        self._last_rx = _t.time()
        while True:
            try:
                chunk = self.ser.read(64)
            except (OSError, serial.SerialException):
                print("[transport] serial lost — reconnecting...")
                self._reopen_serial()
                buf = b""
                self._last_rx = _t.time()
                continue
            # single-threaded TX on the persistent fd. (An afternoon of
            # forensics concluded the CDC link never dropped a byte — the MCU
            # parser just needs compact JSON. See send().)
            try:
                while True:
                    line_out, cmd_out, val_out = self._txq.get_nowait()
                    self.ser.write(line_out)
                    self.ser.flush()
                    if self.observer:
                        self.observer(cmd_out, val_out)
            except queue.Empty:
                pass
            except (OSError, serial.SerialException):
                print("[transport] write failed — reconnecting...")
                self._reopen_serial()
                buf = b""
                self._last_rx = _t.time()
                continue
            if chunk:
                self._last_rx = _t.time()
            # Silent-corpse detection: macOS keeps a stale fd "working" (empty
            # reads, void writes, no errors) after the board resets/replugs.
            # The firmware broadcasts a diag line every 10s — total silence for
            # 25s means this fd is dead. Reopen.
            elif _t.time() - self._last_rx > 25:
                print("[transport] serial silent 25s — stale fd, reopening...")
                try:
                    self.ser.close()
                except Exception:
                    pass
                self._reopen_serial()
                buf = b""
                self._last_rx = _t.time()
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode(errors="ignore").strip())
                    if "e" in msg:
                        self.events.put(msg["e"])
                        if self.observer:
                            self.observer("event", msg["e"])
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # boot noise / partial lines

    def _tcp_loop(self):
        """Connect, read newline-JSON events, reconnect with a short backoff
        on any drop -- a cable wobble or relay restart shouldn't kill the
        brain mid-demo."""
        backoff = 1
        while True:
            try:
                sock = socket.create_connection(
                    (self._tcp_host, self._tcp_port), timeout=5)
                with self._sock_lock:
                    self._sock = sock
                print(f"[transport] TCP connected to "
                      f"{self._tcp_host}:{self._tcp_port}")
                backoff = 1
                buf = b""
                while True:
                    chunk = sock.recv(256)
                    if not chunk:
                        raise ConnectionError("relay closed the connection")
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            msg = json.loads(line.decode(errors="ignore").strip())
                            if "e" in msg:
                                self.events.put(msg["e"])
                                if self.observer:
                                    self.observer("event", msg["e"])
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
            except OSError as e:
                print(f"[transport] TCP link down ({e}) -- "
                      f"retrying in {backoff}s")
                with self._sock_lock:
                    self._sock = None
                time.sleep(backoff)
                backoff = min(backoff * 2, 5)

    def send(self, cmd: str, val: str = ""):
        if MOCK:
            print(f"[MCU] {cmd}={val}")
            if self.observer:
                self.observer(cmd, val)
            return
        payload = {"c": cmd}
        if val:
            payload["v"] = val
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode()  # MCU parser needs COMPACT json: it matches '"c":"' literally
        if TCP_ADDR:
            with self._sock_lock:
                sock = self._sock
            if sock is None:
                return  # link down mid-reconnect -- drop, next one lands
            try:
                sock.sendall(line)
            except OSError:
                return  # _tcp_loop notices on its next recv() and reconnects
        else:
            # macOS CDC: writing while another thread blocks in read() on the
            # same fd silently kills TX. ALL serial I/O lives in _reader now —
            # this just enqueues; observer fires there, after the real write.
            self._txq.put((line, cmd, val))
            return
        if self.observer:
            self.observer(cmd, val)

    def mood(self, m):        self.send("mood", m)
    def text(self, t):
        # OLED caption sanitize: the firmware's hand parser stops at the first
        # '"' inside the value, and its font renders non-ASCII as garbage.
        clean = t.replace('"', "'").encode("ascii", "ignore").decode()
        self.send("text", clean[:150])  # firmware marquees >21
    def beep(self, pattern):  self.send("beep", pattern)

    def next_event(self, timeout=0.1):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None
