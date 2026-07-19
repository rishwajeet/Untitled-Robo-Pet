"""Bridge the MCU's serial link out to the Mac over TCP :8310 -- the
contingency if the board's USB only exposes the Q's Linux/debug side and not
a direct serial passthrough to the Mac (see transport.py's BITTU_TCP mode).
Run on the Q:   adb shell "cd ~/bittu && nohup python3 serial_relay.py /dev/ttyACM0 &"
Then on the Mac: BITTU_TCP=<board-ip>:8310 python3 brain.py
"""
import socket
import sys
import threading
import time

import serial  # pyserial

DEV = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
BAUD = 115200
TCP_PORT = 8310


def open_serial():
    while True:
        try:
            return serial.Serial(DEV, BAUD, timeout=0.1)
        except serial.SerialException as e:
            print(f"serial open failed ({e}), retrying in 2s")
            time.sleep(2)


def serial_to_conn(ser, conn):
    try:
        while True:
            chunk = ser.read(64)
            if chunk:
                conn.sendall(chunk)
    except (OSError, serial.SerialException):
        pass  # conn_to_serial (or the main loop) notices and cleans up


def conn_to_serial(conn, ser):
    while True:
        chunk = conn.recv(256)
        if not chunk:
            raise ConnectionError("client disconnected")
        ser.write(chunk)


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", TCP_PORT))
    srv.listen(1)
    print(f"serial_relay: {DEV} <-> TCP :{TCP_PORT}")
    ser = open_serial()
    while True:
        conn, addr = srv.accept()
        print(f"client connected: {addr}")
        threading.Thread(target=serial_to_conn, args=(ser, conn),
                          daemon=True).start()
        try:
            conn_to_serial(conn, ser)
        except (OSError, ConnectionError) as e:
            print(f"client disconnected ({e})")
        except serial.SerialException as e:
            print(f"serial error ({e}), reopening device")
            ser.close()
            ser = open_serial()
        finally:
            conn.close()


if __name__ == "__main__":
    main()
