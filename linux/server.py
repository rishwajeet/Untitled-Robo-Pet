"""Agent mode — HTTP server so Claude Code (or anything) can drive the robot.

Runs as a thread inside brain.py. Endpoints:

  POST /event   {"e": "agent_start|agent_working|agent_done|agent_error|agent_ask",
                 "text": "short label for the OLED"}
  POST /ask     {"text": "ALLOW rm -rf?"}   -> robot shows question, waits
  GET  /answer  -> {"answer": "yes"|"no"|"pending"}   (talk btn=yes, pet btn=no)
  POST /whatsapp-webhook  receives WHAPI webhook events

Claude Code hooks curl these — see hooks/ for ready-made config.
"""
import hmac
import json
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import swiggy_tool

PORT = int(os.environ.get("PORT", "8300"))
MAX_WEBHOOK_BYTES = 1_000_000
WEBHOOK_SECRET = os.environ.get("WHAPI_WEBHOOK_SECRET", "")

_queue = None          # brain's agent queue
_pending = {"q": None, "answer": None}
_lock = threading.Lock()
_whapi_stats = {"received": 0, "processed": 0, "last_event": None}
_frame_fn = None       # set by brain: () -> latest camera jpeg bytes


def set_frame_source(fn):
    global _frame_fn
    _frame_fn = fn


def put_answer(ans: str):
    """Called by brain when a button is pressed while a question is pending."""
    with _lock:
        if _pending["q"] is not None:
            _pending["answer"] = ans
            _pending["q"] = None


def has_pending() -> bool:
    with _lock:
        return _pending["q"] is not None


def _clean(value, limit=80) -> str:
    """Collapse untrusted webhook text into a safe one-line OLED preview."""
    return " ".join(str(value or "").split())[:limit]


def _message_preview(message: dict) -> str:
    """Extract useful text from common WHAPI message types."""
    message_type = message.get("type", "unknown")
    content = message.get(message_type)
    if message_type == "text":
        return _clean((content or {}).get("body") if isinstance(content, dict) else content)
    if message_type == "link_preview" and isinstance(content, dict):
        return _clean(content.get("body") or content.get("title") or "[link]")
    if message_type == "reply" and isinstance(content, dict):
        button = content.get("buttons_reply") or {}
        return _clean(button.get("title") or content.get("body") or "[reply]")
    if message_type in {"image", "video", "gif", "document"}:
        caption = content.get("caption") if isinstance(content, dict) else None
        return _clean(caption or f"[{message_type}]")
    if message_type in {"audio", "voice"}:
        return f"[{message_type} message]"
    if message_type in {"location", "live_location"} and isinstance(content, dict):
        return _clean(content.get("name") or content.get("address") or "[location]")
    if message_type == "sticker":
        return "[sticker]"
    return f"[{_clean(message_type, 24) or 'message'}]"


def process_whapi_payload(data: dict) -> dict:
    """Normalize a WHAPI callback and enqueue new incoming messages."""
    event = data.get("event") if isinstance(data.get("event"), dict) else {}
    event_type = _clean(event.get("type"), 32) or "unknown"
    event_action = _clean(event.get("event"), 16) or "unknown"
    event_name = f"{event_type}.{event_action}"
    processed = 0

    # messages.post is the new-message event. Statuses and updates are accepted
    # but deliberately do not interrupt the robot.
    if event_type == "messages" and event_action == "post":
        messages = data.get("messages") if isinstance(data.get("messages"), list) else []
        for message in messages:
            if not isinstance(message, dict) or message.get("from_me") is True:
                continue
            sender = _clean(message.get("from_name") or message.get("from") or "WhatsApp", 30)
            preview = _message_preview(message) or "[message]"
            summary = _clean(f"{sender}: {preview}", 100)
            if _queue is not None:
                _queue.put(("whatsapp", "whatsapp_message", summary))
            processed += 1

    with _lock:
        _whapi_stats["received"] += 1
        _whapi_stats["processed"] += processed
        _whapi_stats["last_event"] = event_name
    return {"ok": True, "event": event_name, "processed": processed}


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

    def _path(self):
        return urlsplit(self.path).path.rstrip("/") or "/"

    def _authorized(self):
        if not WEBHOOK_SECRET:
            return True
        supplied = self.headers.get("X-Webhook-Secret", "")
        return hmac.compare_digest(supplied, WEBHOOK_SECRET)

    def _read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, "invalid content length"
        if size > MAX_WEBHOOK_BYTES:
            return None, "payload too large"
        try:
            data = json.loads(self.rfile.read(size) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, "invalid JSON"
        if not isinstance(data, dict):
            return None, "JSON body must be an object"
        return data, None

    def _handle_whapi(self):
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        data, error = self._read_json()
        if error:
            code = 413 if error == "payload too large" else 400
            self._json(code, {"ok": False, "error": error})
            return
        self._json(200, process_whapi_payload(data))

    def do_POST(self):
        if self._path() == "/whatsapp-webhook":
            self._handle_whapi()
            return
        data, error = self._read_json()
        if error:
            self._json(400, {"ok": False, "error": error})
            return
        path = self._path()
        if path == "/event":
            _queue.put(("agent", data.get("e", "agent_working"),
                        data.get("text", "")[:21]))
            self._json(200, {"ok": True})
        elif path == "/ask":
            with _lock:
                _pending["q"] = data.get("text", "ALLOW?")[:21]
                _pending["answer"] = None
            _queue.put(("agent", "agent_ask", _pending["q"]))
            self._json(200, {"ok": True})
        # ---- dashboard control plane (all inputs work from the browser) ----
        elif path == "/say":       # typed chat -> full think+speak flow
            text = (data.get("text") or "").strip()
            if text:
                _queue.put(("control", "say", text[:500]))
            self._json(200, {"ok": bool(text)})
        elif path == "/listen":    # remote push-to-talk (records at the robot)
            _queue.put(("control", "listen", ""))
            self._json(200, {"ok": True})
        elif path == "/command":   # raw body control: mood/face/beep/text
            c, v = data.get("c", ""), data.get("v", "")
            if c in ("mood", "face", "beep", "text", "reinit", "ping"):
                _queue.put(("control", "command", json.dumps({"c": c, "v": v})))
                self._json(200, {"ok": True})
            else:
                self._json(400, {"ok": False, "error": "unknown command"})
        elif path == "/guard":
            _queue.put(("control", "guard",
                        "on" if data.get("on") in (True, "true", "on", 1) else "off"))
            self._json(200, {"ok": True})
        elif path == "/answer":    # web mirror of the physical yes/no buttons
            ans = data.get("answer", "")
            if ans in ("yes", "no"):
                put_answer(ans)
                _queue.put(("control", "web_answer", ans))
                self._json(200, {"ok": True})
            else:
                self._json(400, {"ok": False})
        else:
            self._json(404, {})

    def do_PUT(self):
        if self._path() == "/whatsapp-webhook":
            self._handle_whapi()
        else:
            self._json(404, {})

    def do_PATCH(self):
        self.do_PUT()

    def do_DELETE(self):
        self.do_PUT()

    def do_GET(self):
        path = self._path()
        if path == "/swiggy/auth":
            try:
                self.send_response(302)
                self.send_header("Location", swiggy_tool.begin_auth())
                self.end_headers()
            except Exception as exc:
                self._json(502, {"ok": False, "error": str(exc)})
        elif path == "/swiggy/callback":
            query = parse_qs(urlsplit(self.path).query)
            try:
                swiggy_tool.finish_auth(query.get("code", [""])[0],
                                        query.get("state", [""])[0])
                body = b"Swiggy connected to Bittu. You can close this tab."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self._json(400, {"ok": False, "error": str(exc)})
        elif path == "/swiggy/status":
            self._json(200, {"ok": True, **swiggy_tool.auth_status()})
        elif path == "/answer":
            with _lock:
                ans = _pending["answer"]
                q = _pending["q"]
            self._json(200, {"answer": ans or "pending", "question": q})
        elif path == "/frame":
            jpeg = _frame_fn() if _frame_fn else None
            if jpeg:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(jpeg)
            else:
                self._json(404, {"ok": False, "error": "no frame yet"})
        elif self._path() == "/whatsapp-webhook":
            with _lock:
                stats = dict(_whapi_stats)
            self._json(200, {"ok": True, "service": "whapi-webhook", **stats})
        else:
            self._json(200, {"robot": "bittu", "ok": True})


def create_server(agent_queue, host="0.0.0.0", port=PORT):
    global _queue
    _queue = agent_queue
    return ThreadingHTTPServer((host, port), Handler)


def start(agent_queue):
    srv = create_server(agent_queue)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Agent mode listening on :{PORT}")
    return srv


def main():
    """Run only the HTTP receiver, useful on a laptop behind ngrok."""
    events = queue.Queue()
    srv = create_server(events)
    print(f"Bittu webhook server listening on http://0.0.0.0:{PORT}")
    print("WHAPI route: /whatsapp-webhook")
    print(f"Swiggy login: http://localhost:{PORT}/swiggy/auth")

    def print_events():
        while True:
            source, event, text = events.get()
            print(f"[{source}] {event}: {text}")

    threading.Thread(target=print_events, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
