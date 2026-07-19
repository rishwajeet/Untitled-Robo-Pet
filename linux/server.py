"""Agent mode — HTTP server so Claude Code (or anything) can drive the robot.

Runs as a thread inside brain.py. Endpoints:

  POST /event   {"e": "agent_start|agent_working|agent_done|agent_error|agent_ask",
                 "text": "short label for the OLED"}
  POST /ask     {"text": "ALLOW rm -rf?"}   -> robot shows question, waits
  GET  /answer  -> {"answer": "yes"|"no"|"pending"}   (talk btn=yes, pet btn=no)

Claude Code hooks curl these — see hooks/ for ready-made config.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8300

_queue = None          # brain's agent queue
_pending = {"q": None, "answer": None}
_lock = threading.Lock()


def put_answer(ans: str):
    """Called by brain when a button is pressed while a question is pending."""
    with _lock:
        if _pending["q"] is not None:
            _pending["answer"] = ans
            _pending["q"] = None


def has_pending() -> bool:
    with _lock:
        return _pending["q"] is not None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence request logging
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            data = {}
        if self.path == "/event":
            _queue.put(("agent", data.get("e", "agent_working"),
                        data.get("text", "")[:21]))
            self._json(200, {"ok": True})
        elif self.path == "/ask":
            with _lock:
                _pending["q"] = data.get("text", "ALLOW?")[:21]
                _pending["answer"] = None
            _queue.put(("agent", "agent_ask", _pending["q"]))
            self._json(200, {"ok": True})
        else:
            self._json(404, {})

    def do_GET(self):
        if self.path == "/answer":
            with _lock:
                ans = _pending["answer"]
            self._json(200, {"answer": ans or "pending"})
        else:
            self._json(200, {"robot": "bittu", "ok": True})


def start(agent_queue):
    global _queue
    _queue = agent_queue
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Agent mode listening on :{PORT}")
