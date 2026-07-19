"""Laptop-side bridge: Bittu -> live Claude Code session, via tmux.

On the Mac:
  1. tmux new -s claude        # inside it: claude   (start your session)
  2. python3 bridge.py         # listens on :8400
  3. On the Q: export BRIDGE_URL=http://<laptop-ip>:8400
Now "tell claude to ..." spoken to Bittu lands in the session as a prompt;
"stop him" sends Escape. Claude's lifecycle flows back via hooks.
"""
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SESSION = "claude"
PORT = 8400


def tmux(*args):
    subprocess.run(["tmux", *args], capture_output=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            data = {}
        if self.path == "/prompt":
            text = data.get("text", "").strip()
            if text:
                tmux("send-keys", "-t", SESSION, "-l", "--", text)  # -- : text starting with "-" isn't a flag
                tmux("send-keys", "-t", SESSION, "Enter")
                print(f"-> claude: {text}")
        elif self.path == "/interrupt":
            tmux("send-keys", "-t", SESSION, "Escape")
            print("-> claude: ESC")
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


print(f"Bridge to tmux session '{SESSION}' on :{PORT}")
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
