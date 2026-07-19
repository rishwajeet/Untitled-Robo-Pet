"""Stream TTS audio from the UNO Q to the Glyph C6 voice box over TCP.

Set C6_IP to the address the Glyph prints on boot. Same network as the Q
(use the phone hotspot for both — venue WiFi may isolate clients).
"""
import os
import socket

C6_IP = os.environ.get("C6_IP", "")
C6_PORT = 8301
WAV_HEADER = 44  # strip standard wav header, C6 wants raw PCM


def play_wav(path: str) -> bool:
    if not C6_IP:
        return False
    try:
        with open(path, "rb") as f:
            pcm = f.read()[WAV_HEADER:]
        with socket.create_connection((C6_IP, C6_PORT), timeout=3) as s:
            s.sendall(pcm)
        return True
    except OSError as e:
        print(f"C6 audio failed: {e}")
        return False
