"""Live view of Bittu's inner life — the demo-table dashboard.

Serves one self-contained page (GET /) that polls GET /feed?since=N for new
journal lines and renders them as a running transcript, styled per entry
kind. Stdlib http.server only — no Flask, no external requests, safe on the
2GB board. Run alongside brain.py:

    JOURNAL=~/bittu-journal.jsonl python3 dashboard.py   (defaults to :8302)

Then open http://<board-ip>:8302 on the laptop/phone next to the robot.
"""
import base64
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import journal

PORT = int(os.environ.get("DASHBOARD_PORT", 8302))
BRAIN = os.environ.get("BRAIN_URL", "http://127.0.0.1:8300")  # server.py in brain.py

# ---- real OLED face art, embedded so the virtual OLED shows the exact bitmaps
# the physical screen renders (assets/faces/generated/*.png, ~200B each, 1-bit
# 128x32). Read once at import; a missing/renamed file just drops that key —
# the page's JS falls back to the CSS eye mimic when a name has no entry.
_FACE_NAMES = (
    "idle", "blink", "happy", "surprised", "waiting", "error", "sleeping",
    "speaking", "listening", "working",
    "claude_permission", "claude_tool_running", "claude_done",
    "claude_needs_input", "claude_rate_limited", "claude_disconnected",
)


def _load_face_uris() -> dict:
    base = os.path.join(os.path.dirname(__file__), "..", "assets", "faces", "generated")
    out = {}
    for name in _FACE_NAMES:
        try:
            with open(os.path.join(base, name + ".png"), "rb") as f:
                out[name] = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
        except OSError:
            pass  # asset missing/renamed — JS treats an absent key as "no bitmap"
    return out


FACE_URIS = _load_face_uris()

_lock = threading.Lock()
# Incremental read state: byte offset we've consumed up to, and every entry
# parsed so far. /feed just slices this list — the journal file itself is
# only ever seeked from the last offset, never re-read from the top, so a
# 1s poll stays cheap no matter how long the demo runs.
_cache = {"offset": 0, "entries": []}


def _pull_new_entries():
    try:
        size = os.path.getsize(journal.PATH)
    except OSError:
        return  # nothing logged yet
    with _lock:
        if size < _cache["offset"]:  # journal truncated/rotated underneath us
            _cache["offset"] = 0
            _cache["entries"] = []
        if size == _cache["offset"]:
            return
        with open(journal.PATH, "rb") as f:
            f.seek(_cache["offset"])
            chunk = f.read()
            _cache["offset"] = f.tell()
        for raw in chunk.decode("utf-8", "replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                _cache["entries"].append(json.loads(raw))
            except json.JSONDecodeError:
                continue  # a line written mid-append — skip, next poll gets it whole


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence request logging
        pass

    # ---- proxy to the brain's control server (same-origin for the browser) ----
    def _proxy(self, method, subpath, body=None):
        req = urllib.request.Request(BRAIN + subpath, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                payload = r.read()
                ctype = r.headers.get("Content-Type", "application/json")
                self.send_response(r.status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
        except Exception as e:
            self._json(502, {"ok": False, "error": f"brain unreachable: {e}"})

    def do_POST(self):
        parts = urlsplit(self.path)
        if parts.path.startswith("/api/"):
            n = int(self.headers.get("Content-Length", 0) or 0)
            self._proxy("POST", parts.path[4:], self.rfile.read(n) if n else b"{}")
        else:
            self._json(404, {"error": "not found"})

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == "/":
            self._html(200, PAGE)
        elif parts.path.startswith("/api/"):
            self._proxy("GET", parts.path[4:])
        elif parts.path == "/feed":
            qs = parse_qs(parts.query)
            try:
                since = max(0, int(qs.get("since", ["0"])[0]))
            except ValueError:
                since = 0
            _pull_new_entries()
            with _lock:
                entries = _cache["entries"][since:]
                total = len(_cache["entries"])
            self._json(200, {"total": total, "entries": entries})
        elif parts.path == "/status":
            self._proxy("GET", "/status")
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code, html):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Bittu — inner life</title>
<style>
:root{
  --bg:#0a0b0f; --panel:#111420; --ink:#e9ecf1;
  --dim:#606a78; --dimmer:#3c4552; --line:#1b2029;
  --teal:#4fe8c8; --violet:#9b8cfb; --amber:#f2b344; --rose:#f572a8; --red:#ef5757;
}
*{box-sizing:border-box;}
html,body{height:100%;}
body{
  margin:0; min-height:100%; display:flex; flex-direction:column;
  color:var(--ink); background:
    radial-gradient(ellipse at 50% -10%, rgba(79,232,200,.07), transparent 55%),
    var(--bg);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
  -webkit-font-smoothing:antialiased;
}
header{
  position:sticky; top:0; z-index:5; display:flex; flex-direction:column; gap:8px;
  padding:14px 18px; background:linear-gradient(var(--panel), rgba(17,20,32,.94));
  border-bottom:1px solid var(--line); backdrop-filter:blur(6px);
}
.services{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px;
  padding:12px 16px 6px; max-width:1100px; width:100%; margin:0 auto;}
.service{min-width:0; padding:10px 12px; border:1px solid var(--line); border-radius:9px;
  background:rgba(17,20,32,.78);}
.service-name{font-size:9px; font-weight:750; color:var(--dim); letter-spacing:.12em;
  text-transform:uppercase; margin-bottom:5px;}
.service-state{display:flex; align-items:center; gap:7px; font-size:13px; font-weight:700;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.service-state::before{content:""; width:7px; height:7px; flex:none; border-radius:50%;
  background:var(--teal); box-shadow:0 0 7px rgba(79,232,200,.55);}
.service.warn .service-state::before{background:var(--amber); box-shadow:none;}
.service.off .service-state::before{background:var(--dimmer); box-shadow:none;}
.service.bad .service-state::before{background:var(--red); box-shadow:none;}
@media(max-width:700px){.services{grid-template-columns:repeat(2,minmax(0,1fr));}}
.hardware{display:grid; grid-template-columns:minmax(260px,1.4fr) minmax(220px,1fr);
  gap:12px; padding:10px 16px 14px; max-width:1100px; width:100%; margin:0 auto;
  border-bottom:1px solid var(--line);}
.hardware h2{font-size:10px; color:var(--dim); letter-spacing:.13em; text-transform:uppercase;
  margin:0 0 8px; font-weight:750;}
.oled-shell{background:#050606; border:5px solid #262b32; border-radius:8px; padding:7px;
  box-shadow:inset 0 0 18px rgba(0,0,0,.9);}
.oled-screen{position:relative; height:82px; overflow:hidden; color:#b9fff2;
  background:radial-gradient(ellipse at center,rgba(79,232,200,.09),transparent 70%),#020807;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; text-shadow:0 0 7px rgba(79,232,200,.75);}
.oled-face-wrap{height:60px; display:flex; align-items:center; justify-content:center;}
.oled-face-img{width:100%; height:100%; object-fit:contain;
  image-rendering:pixelated; image-rendering:crisp-edges;
  filter:drop-shadow(0 0 2px rgba(185,255,242,.9)) drop-shadow(0 0 6px rgba(79,232,200,.6));}
.oled-face-img[hidden]{display:none;}
.eyes{height:52px; display:flex; align-items:center; justify-content:center; gap:45px;}
.eye{width:27px; height:24px; border:4px solid currentColor; border-radius:50%;
  transition:all .2s ease;}
.eyes.sleepy .eye{height:4px; border-width:0 0 4px; border-radius:0;}
.eyes.love .eye{border-radius:55% 55% 45% 45%; transform:rotate(45deg); width:20px; height:20px;}
.eyes.dizzy .eye{border-radius:0; transform:rotate(45deg); width:18px; height:18px;}
.eyes.angry .eye{height:14px; border-radius:4px; transform:skewY(-12deg);}
.eyes.surprised .eye{width:25px; height:30px;}
.oled-caption{text-align:center; height:22px; padding:1px 5px; overflow:hidden;
  white-space:nowrap; font-size:12px; text-transform:uppercase;}
.oled-caption span{display:inline-block; max-width:100%; overflow:hidden; text-overflow:ellipsis;}
.oled-caption.marquee{text-align:left;}
.oled-caption.marquee span{max-width:none; text-overflow:clip; padding-left:100%;
  animation:oledscroll linear infinite;}
@keyframes oledscroll{from{transform:translateX(0)}to{transform:translateX(-100%)}}
.hardware-side{display:flex; flex-direction:column; justify-content:space-between; gap:12px;}
.outputs{display:flex; align-items:flex-end; justify-content:space-around; gap:12px; min-height:64px;}
.output{text-align:center; color:var(--dim); font-size:9px; letter-spacing:.08em; text-transform:uppercase;}
.led{width:22px; height:22px; margin:0 auto 7px; border-radius:50%; background:#281112;
  border:2px solid #343840; transition:background .25s,box-shadow .25s,opacity .25s; opacity:.4;}
.led.blue{background:#10172a}.led.on.red{background:#ff4b55;box-shadow:0 0 18px #ff313e;opacity:1}
.led.on.blue{background:#4a8cff;box-shadow:0 0 18px #337dff;opacity:1}
.led.dim{opacity:.65}.led.alt{animation:ledpulse 1s ease-in-out infinite alternate}
@keyframes ledpulse{from{opacity:.25}to{opacity:1}}
.speaker{width:34px;height:34px;margin:0 auto 2px;position:relative;color:var(--dim)}
.speaker::before{content:"";position:absolute;left:4px;top:10px;width:9px;height:14px;background:currentColor}
.speaker::after{content:"";position:absolute;left:10px;top:6px;border-style:solid;border-width:11px 14px 11px 0;
  border-color:transparent currentColor transparent transparent;transform:rotate(180deg)}
.speaker.on{color:var(--amber);animation:sound .35s ease-in-out infinite alternate}
@keyframes sound{to{filter:drop-shadow(0 0 7px var(--amber));transform:scale(1.08)}}
.last-action{font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--dim);
  padding-top:8px;border-top:1px solid var(--line);overflow-wrap:anywhere;}
@media(max-width:700px){.hardware{grid-template-columns:1fr}.oled-screen{height:72px}}
.top{display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;}
.brand{display:flex; align-items:baseline; gap:10px;}
.brand h1{font-size:16px; letter-spacing:.16em; margin:0; font-weight:800;}
.brand .sub{font-size:11px; color:var(--dim); letter-spacing:.08em; text-transform:uppercase;}
.status{display:flex; align-items:center; gap:8px; font-size:11px; color:var(--dim);
  letter-spacing:.06em; text-transform:uppercase; white-space:nowrap;}
.dot{width:8px; height:8px; border-radius:50%; background:var(--teal);
  box-shadow:0 0 8px var(--teal); animation:blink 1.6s ease-in-out infinite; flex:none;}
.dot.down{background:var(--red); box-shadow:0 0 8px var(--red); animation:none; opacity:.55;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.count{opacity:.7;}
.mood{display:flex; align-items:baseline; gap:10px;}
.mood-label{font-size:10px; color:var(--dim); text-transform:uppercase; letter-spacing:.16em;}
.mood-word{font-weight:800; font-size:clamp(24px,6vw,38px); letter-spacing:.01em;
  transition:color .4s ease;}
.mood-word.pulse{animation:pulse .5s ease;}
@keyframes pulse{0%{opacity:.5; transform:translateY(3px)}100%{opacity:1; transform:translateY(0)}}

main#feed{flex:1; overflow-y:auto; padding:10px 16px 90px; -webkit-overflow-scrolling:touch;}
main#feed::-webkit-scrollbar{width:6px;}
main#feed::-webkit-scrollbar-thumb{background:var(--line); border-radius:3px;}

.row{display:flex; gap:10px; align-items:baseline; padding:5px 8px; margin-top:1px;
  border-left:2px solid transparent; border-radius:3px; font-size:14px; line-height:1.45;}
.time{flex:0 0 60px; color:var(--dim); opacity:.6; font:12px/1 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
.tag{flex:0 0 auto; align-self:center; font-size:10px; font-weight:700; letter-spacing:.08em;
  padding:2px 6px; border-radius:4px; color:var(--dim); background:rgba(255,255,255,.04);}
.text{flex:1; min-width:0; overflow-wrap:anywhere; color:#c9cdd5;}

.k-said{border-left-color:var(--teal); background:rgba(79,232,200,.04);}
.k-said .tag{color:var(--teal); background:rgba(79,232,200,.12);}
.k-said .text{color:var(--ink); font-weight:600; font-size:15px;}

.k-heard .tag, .k-event .tag{color:#9aa3ad; background:rgba(255,255,255,.05);}

.k-heartbeat .text{font-style:italic; color:#8b93a5;}
.k-heartbeat .tag{color:#8b93a5; background:rgba(255,255,255,.04);}
.k-heartbeat.idle{opacity:.5;}
.k-heartbeat.idle .text{font-size:12.5px;}

.k-tool .text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12.5px;
  color:var(--amber); opacity:.9;}
.k-tool .tag{color:var(--amber); background:rgba(242,179,68,.12);}

.k-agent{border-left-color:var(--violet); background:rgba(155,140,251,.04);}
.k-agent .tag{color:var(--violet); background:rgba(155,140,251,.12);}
.k-agent .text{color:#d8d3fc;}

.k-touch .tag{color:var(--rose); background:rgba(245,114,168,.12);}
.k-touch .text{color:var(--rose); font-weight:600;}

.k-guard .tag{color:var(--red); background:rgba(239,87,87,.12);}
.k-guard .text{color:#f0a0a0;}

.k-touch.alert, .k-guard.alert{border-left-color:var(--red); background:rgba(239,87,87,.09);}
.k-touch.alert .tag, .k-guard.alert .tag{color:var(--red); background:rgba(239,87,87,.18);}
.k-touch.alert .text, .k-guard.alert .text{color:var(--red); font-weight:700;}

.k-system .text{color:var(--dim); text-transform:uppercase; font-size:11.5px; letter-spacing:.06em;}
.k-system .tag{color:var(--dim);}
.placeholder .text{font-style:italic; color:var(--dimmer); text-transform:none; letter-spacing:0;}

#resume{
  position:fixed; left:50%; bottom:178px; transform:translateX(-50%);
  padding:8px 16px; border-radius:999px; border:1px solid var(--line);
  background:rgba(17,20,32,.92); color:var(--teal); font-size:12px; font-weight:700;
  letter-spacing:.03em; cursor:pointer; box-shadow:0 6px 20px rgba(0,0,0,.35);
}
#resume[hidden]{display:none;}

/* ---- cockpit ---- */
#console{
  position:fixed; left:0; right:0; bottom:0; z-index:6;
  background:linear-gradient(rgba(17,20,32,.96), var(--panel));
  border-top:1px solid var(--line); backdrop-filter:blur(8px);
  padding:10px 14px calc(10px + env(safe-area-inset-bottom));
  display:flex; flex-direction:column; gap:8px;
}
.chatrow{display:flex; gap:8px;}
.chatrow input{
  flex:1; min-width:0; background:var(--bg); color:var(--ink);
  border:1px solid var(--line); border-radius:8px; padding:10px 12px;
  font-size:14px; outline:none;
}
.chatrow input:focus{border-color:var(--teal);}
.btn{
  border:1px solid var(--line); background:rgba(255,255,255,.05); color:var(--ink);
  border-radius:8px; padding:9px 14px; font-size:13px; font-weight:700; cursor:pointer;
  letter-spacing:.02em; white-space:nowrap;
}
.btn.primary{background:rgba(79,232,200,.15); color:var(--teal); border-color:rgba(79,232,200,.4);}
.btn.rec{background:rgba(245,114,168,.14); color:var(--rose); border-color:rgba(245,114,168,.4);}
.btn:active{transform:translateY(1px);}
.chips{display:flex; gap:6px; overflow-x:auto; padding-bottom:2px; -webkit-overflow-scrolling:touch;}
.chips::-webkit-scrollbar{display:none;}
.chip{
  flex:none; font-size:11px; font-weight:700; letter-spacing:.05em; cursor:pointer;
  padding:6px 10px; border-radius:999px; border:1px solid var(--line);
  background:rgba(255,255,255,.04); color:#aeb6c2;
}
.chip.mood{color:var(--teal); border-color:rgba(79,232,200,.25);}
.chip.face{color:var(--violet); border-color:rgba(155,140,251,.3);}
.chip.agent{color:var(--amber); border-color:rgba(242,179,68,.3);}
.chip.danger{color:var(--red); border-color:rgba(239,87,87,.35);}
.chip.on{background:rgba(239,87,87,.2); color:var(--red);}
.chip:active{transform:translateY(1px);}
.grouplbl{flex:none; align-self:center; font-size:9px; color:var(--dimmer);
  text-transform:uppercase; letter-spacing:.14em; padding-right:2px;}
#cam{
  position:fixed; right:14px; bottom:186px; z-index:6; width:200px;
  border:1px solid var(--line); border-radius:10px; overflow:hidden;
  box-shadow:0 10px 30px rgba(0,0,0,.5); background:var(--panel);
}
#cam[hidden]{display:none;}
#cam img{display:block; width:100%;}
#cam .camlbl{position:absolute; top:6px; left:8px; font-size:9px; font-weight:800;
  letter-spacing:.12em; color:var(--teal); text-shadow:0 1px 3px rgba(0,0,0,.8);}
#toast{
  position:fixed; left:50%; bottom:186px; transform:translateX(-50%); z-index:7;
  background:rgba(239,87,87,.95); color:#fff; font-size:12px; font-weight:700;
  padding:8px 14px; border-radius:8px; opacity:0; transition:opacity .3s; pointer-events:none;
}
main#feed{padding-bottom:190px;}
</style>
</head>
<body>
<header>
  <div class="top">
    <div class="brand"><h1>BITTU</h1><span class="sub">inner life</span></div>
    <div class="status">
      <span class="dot" id="dot"></span>
      <span id="statusText">LIVE</span>
      <span class="count" id="count"></span>
    </div>
  </div>
  <div class="mood">
    <span class="mood-label">feeling</span>
    <span class="mood-word" id="mood">—</span>
  </div>
</header>
<section class="services" aria-label="Bittu service health">
  <div class="service" data-service="robot"><div class="service-name">Robot USB</div><div class="service-state">checking</div></div>
  <div class="service" data-service="camera"><div class="service-name">Camera</div><div class="service-state">checking</div></div>
  <div class="service" data-service="openai"><div class="service-name">OpenAI</div><div class="service-state">checking</div></div>
  <div class="service" data-service="audio"><div class="service-name">Audio</div><div class="service-state">checking</div></div>
  <div class="service" data-service="swiggy"><div class="service-name">Swiggy MCP</div><div class="service-state">checking</div></div>
  <div class="service" data-service="whapi"><div class="service-name">WhatsApp</div><div class="service-state">checking</div></div>
  <div class="service" data-service="bridge"><div class="service-name">Claude Bridge</div><div class="service-state">checking</div></div>
  <div class="service" data-service="uptime"><div class="service-name">Mac service</div><div class="service-state">starting</div></div>
</section>
<section class="hardware" aria-label="Expected Arduino outputs">
  <div>
    <h2>Expected OLED</h2>
    <div class="oled-shell"><div class="oled-screen">
      <div class="oled-face-wrap">
        <img class="oled-face-img" id="oledFaceImg" alt="" hidden>
        <div class="eyes idle" id="oledEyes" aria-label="Expected OLED face"><span class="eye"></span><span class="eye"></span></div>
      </div>
      <div class="oled-caption" id="oledText"><span id="oledTextInner">BITTU</span></div>
    </div></div>
  </div>
  <div class="hardware-side">
    <div>
      <h2>Expected outputs</h2>
      <div class="outputs">
        <div class="output"><div class="led red" id="ledR1"></div>Red 1</div>
        <div class="output"><div class="led red" id="ledR2"></div>Red 2</div>
        <div class="output"><div class="led blue" id="ledB1"></div>Blue 1</div>
        <div class="output"><div class="led blue" id="ledB2"></div>Blue 2</div>
        <div class="output"><div class="speaker" id="speaker"></div>Speaker</div>
      </div>
    </div>
    <div class="last-action" id="lastHardware">waiting for robot</div>
  </div>
</section>
<main id="feed">
  <div class="row k-system placeholder">
    <span class="time"></span><span class="tag">SYSTEM</span>
    <span class="text">waiting for signs of life…</span>
  </div>
</main>
<button id="resume" hidden>new entries ↓</button>

<div id="cam"><span class="camlbl">HIS EYES</span><img id="camimg" alt="camera"></div>
<div id="toast"></div>

<div id="console">
  <div class="chatrow">
    <input id="chat" type="text" placeholder="talk to Bittu… (or press LISTEN and speak)" autocomplete="off">
    <button class="btn primary" id="send">SEND</button>
    <button class="btn rec" id="listen">LISTEN</button>
  </div>
  <div class="chips">
    <span class="grouplbl">mood</span>
    <span class="chip mood" data-cmd="mood:happy">HAPPY</span>
    <span class="chip mood" data-cmd="mood:surprised">SURPRISED</span>
    <span class="chip mood" data-cmd="mood:angry">ANGRY</span>
    <span class="chip mood" data-cmd="mood:love">LOVE</span>
    <span class="chip mood" data-cmd="mood:dizzy">DIZZY</span>
    <span class="chip mood" data-cmd="mood:sleepy">SLEEPY</span>
    <span class="chip mood" data-cmd="beep:happy">BEEP</span>
    <span class="chip" id="caption">CAPTION↵</span>
  </div>
  <div class="chips">
    <span class="grouplbl">agent</span>
    <span class="chip face" data-cmd="face:claude_tool_running">WORKING</span>
    <span class="chip face" data-cmd="face:claude_done">DONE</span>
    <span class="chip face" data-cmd="face:claude_permission">PERMISSION</span>
    <span class="chip agent" data-event="agent_start:demo task">STAGE START</span>
    <span class="chip agent" data-event="agent_done:tests green!">STAGE DONE</span>
    <span class="chip agent" data-event="agent_ask:ALLOW demo cmd?">STAGE ASK</span>
    <span class="chip mood" id="ansYes">YES</span>
    <span class="chip danger" id="ansNo">NO</span>
    <span class="grouplbl">sys</span>
    <span class="chip danger" id="guard">GUARD</span>
    <span class="chip" id="camToggle">CAM</span>
    <span class="chip face" id="modeToggle">MODE</span>
    <span class="chip danger" id="reload">RELOAD</span>
  </div>
</div>
<script>
(function(){
"use strict";
var feed = document.getElementById("feed");
var moodEl = document.getElementById("mood");
var dot = document.getElementById("dot");
var statusText = document.getElementById("statusText");
var countEl = document.getElementById("count");
var resumeBtn = document.getElementById("resume");

var since = 0;
var stick = true;
var firstLoad = true;
var placeholderGone = false;

// ---- real OLED face art (server-embedded data URIs; empty object if assets
// were missing at boot, in which case every lookup below misses and the CSS
// eye mimic renders instead — same fallback path, no separate code path).
var FACES = "__FACE_DATA_URIS__";
var MOOD_TO_FACE = {happy:"happy", curious:"waiting", attentive:"waiting",
  angry:"error", sleepy:"sleeping", surprised:"surprised", idle:"idle"};

// idle blink: firmware blinks every ~2-5s for ~120ms (nextBlink = now + 2000
// + now%3000). We don't have its exact phase, just its distribution, so a
// randomized repeat is the honest equivalent rather than a fixed cadence.
var blinkOn = false;
function scheduleBlink(){
  setTimeout(function(){
    blinkOn = true; renderFace();
    setTimeout(function(){ blinkOn = false; renderFace(); }, 120);
    scheduleBlink();
  }, 2000 + Math.random() * 3000);
}
scheduleBlink();

var lastHW = {};
function renderFace(){
  var h = lastHW;
  var mood = String(h.mood || "idle").toLowerCase();
  var face = String(h.face || "");
  var img = document.getElementById("oledFaceImg");
  var eyes = document.getElementById("oledEyes");

  // CSS-eye approximation for the rare case a bitmap is missing — same mood
  // buckets an agent face implies, so the fallback still reads as intended.
  var faceLabel = face.replace(/^claude_/, "").replace(/_/g, " ");
  var cssMood = mood;
  if (/done/.test(faceLabel)) cssMood = "love";
  else if (/permission|needs input/.test(faceLabel)) cssMood = "surprised";
  else if (/tool|working/.test(faceLabel)) cssMood = "curious";
  else if (/error|disconnected|rate limited/.test(faceLabel)) cssMood = "angry";

  // priority mirrors drawEyes(): agent face override > mood bitmap > love/dizzy
  var bitmapName = null;
  if (face && FACES[face]) {
    bitmapName = face;
  } else if (mood !== "love" && mood !== "dizzy") {
    var key = mood === "attentive" ? "curious" : mood;
    bitmapName = (key === "idle" && blinkOn && FACES.blink) ? "blink" : (MOOD_TO_FACE[key] || "idle");
    if (!FACES[bitmapName]) bitmapName = null;
  }

  if (bitmapName) {
    img.src = FACES[bitmapName];
    img.hidden = false;
    eyes.style.display = "none";
  } else {
    img.hidden = true;
    eyes.style.display = "";
    eyes.className = "eyes " + cssMood;
  }
}

function setCaption(text){
  var band = document.getElementById("oledText");
  var inner = document.getElementById("oledTextInner");
  inner.textContent = text;
  var marquee = text.length > 21;
  band.classList.toggle("marquee", marquee);
  inner.style.animationDuration = marquee ? (Math.max(3, (text.length + 3) * 0.22) + "s") : "";
}

var TAG = {system:"SYSTEM", heard:"HEARD", event:"HEARD", said:"SAID",
  touch:"TOUCH", heartbeat:"THOUGHT", tool:"TOOL", agent:"AGENT", guard:"GUARD"};

var TOUCH_MOOD = {pickup:"SURPRISED", shake:"DIZZY", tap:"LOVED", pet:"LOVED",
  dark:"SLEEPY", greet:"HAPPY"};
var AGENT_MOOD = {agent_start:"FOCUSED", agent_working:"FOCUSED", agent_done:"PROUD",
  agent_error:"RATTLED", agent_ask:"UNSURE"};
var AGENT_LABEL = {agent_start:"started", agent_working:"working", agent_done:"done",
  agent_error:"error", agent_ask:"asking"};
var MOOD_COLOR = {
  ALARMED:"var(--red)", GUARDING:"var(--red)", DIZZY:"var(--red)", RATTLED:"var(--red)",
  LOVED:"var(--rose)", PROUD:"var(--rose)", SURPRISED:"var(--amber)", UNSURE:"var(--amber)",
  BUSY:"var(--amber)", FOCUSED:"var(--violet)", IDLE:"var(--dim)", SLEEPY:"var(--dim)",
  MUSING:"var(--teal)", CURIOUS:"var(--teal)", HAPPY:"var(--teal)"
};

function isAlert(e){
  var t = (e.text || "");
  if (e.kind === "touch") return t === "shake";
  if (e.kind === "guard") return /MOTION|INTRUDER/i.test(t);
  return false;
}

function deriveMood(e){
  if (e.mood) return String(e.mood).toUpperCase();
  switch (e.kind) {
    case "system": return "AWAKE";
    case "heard": case "event": return "LISTENING";
    case "said": return "SPEAKING";
    case "tool": return "BUSY";
    case "guard": return /MOTION|INTRUDER/i.test(e.text || "") ? "ALARMED" : "GUARDING";
    case "touch": return TOUCH_MOOD[e.text] || "CURIOUS";
    case "heartbeat": return e.text === "(nothing worth doing)" ? "IDLE" : "MUSING";
    case "agent": {
      var key = (e.text || "").split(":")[0].trim();
      return AGENT_MOOD[key] || "FOCUSED";
    }
    default: return "AWAKE";
  }
}

function formatText(e){
  if (e.kind === "agent") {
    var idx = (e.text || "").indexOf(":");
    var key = idx === -1 ? e.text : e.text.slice(0, idx).trim();
    var detail = idx === -1 ? "" : e.text.slice(idx + 1).trim();
    var label = AGENT_LABEL[key] || key;
    return detail ? (label + " — " + detail) : label;
  }
  return e.text || "";
}

function updateMood(e){
  var mood = deriveMood(e);
  moodEl.textContent = mood;
  moodEl.style.color = MOOD_COLOR[mood] || "var(--ink)";
  moodEl.classList.remove("pulse");
  void moodEl.offsetWidth;
  moodEl.classList.add("pulse");
}

function renderEntry(e){
  var row = document.createElement("div");
  var cls = "row k-" + (e.kind || "event");
  if (isAlert(e)) cls += " alert";
  if (e.kind === "heartbeat" && e.text === "(nothing worth doing)") cls += " idle";
  row.className = cls;

  var time = document.createElement("span");
  time.className = "time";
  time.textContent = e.t || "";

  var tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent = TAG[e.kind] || (e.kind || "?").toUpperCase();

  var text = document.createElement("span");
  text.className = "text";
  text.textContent = formatText(e);

  row.appendChild(time);
  row.appendChild(tag);
  row.appendChild(text);
  return row;
}

function scrollToBottom(){ feed.scrollTop = feed.scrollHeight; }

function trimFeed(){
  while (feed.children.length > 300) feed.removeChild(feed.firstChild);
}

feed.addEventListener("scroll", function(){
  var gap = feed.scrollHeight - feed.scrollTop - feed.clientHeight;
  stick = gap < 60;
  resumeBtn.hidden = stick;
});
resumeBtn.addEventListener("click", function(){
  stick = true;
  resumeBtn.hidden = true;
  scrollToBottom();
});

function setConnected(ok){
  dot.classList.toggle("down", !ok);
  statusText.textContent = ok ? "LIVE" : "RECONNECTING";
}

function setService(name, label, state){
  var card = document.querySelector('[data-service="' + name + '"]');
  if (!card) return;
  card.className = "service" + (state ? " " + state : "");
  card.querySelector(".service-state").textContent = label;
}

function duration(total){
  total = Number(total || 0);
  var h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60);
  return h ? h + "h " + m + "m" : Math.max(0, m) + "m";
}

function expectedOutputs(h){
  h = h || {};
  lastHW = h;
  var mood = String(h.mood || "idle").toLowerCase();
  renderFace();
  var fresh = Number(h.text_until || 0) > Date.now() / 1000;
  var faceLabel = String(h.face || "").replace(/^claude_/, "").replace(/_/g, " ");
  setCaption(fresh ? (h.text || "") : (faceLabel || mood));
  ["ledR1","ledR2","ledB1","ledB2"].forEach(function(id){
    document.getElementById(id).className = "led " + (id.indexOf("R") > -1 ? "red" : "blue");
  });
  function on(id, extra){ document.getElementById(id).classList.add("on"); if(extra) document.getElementById(id).classList.add(extra); }
  if (mood === "angry") { on("ledR1"); on("ledR2"); }
  else if (mood === "surprised") { on("ledR1","alt"); on("ledB2","alt"); }
  else if (mood === "sleepy") { on("ledB1","dim"); on("ledB2","dim"); }
  else if (mood === "dizzy") { on("ledR1","alt"); on("ledR2","alt"); }
  else { on("ledB1", mood === "idle" ? "alt" : ""); on("ledB2", mood === "idle" ? "alt" : ""); if(mood === "love") on("ledR1","dim"); }
  var sounding = h.beep && Number(h.beep_until || 0) > Date.now() / 1000;
  document.getElementById("speaker").className = "speaker" + (sounding ? " on" : "");
  document.getElementById("lastHardware").textContent = (h.last_action || "waiting for robot") + " · mood " + mood;
}

function pollStatus(){
  fetch("/status", {cache:"no-store"}).then(function(r){
    if (!r.ok) throw new Error("offline");
    return r.json();
  }).then(function(s){
    setService("robot", s.runtime.robot ? "connected" : "not connected", s.runtime.robot ? "" : "bad");
    setService("camera", s.runtime.camera ? "video ready" : "not available", s.runtime.camera ? "" : "bad");
    setService("openai", s.openai ? "key loaded" : "key missing", s.openai ? "" : "bad");
    setService("audio", s.audio === "beeps" ? "beeps only" : s.audio, s.audio === "beeps" ? "warn" : "");
    setService("swiggy", s.swiggy.authenticated ? "authenticated" : "login needed", s.swiggy.authenticated ? "" : "warn");
    setService("whapi", (s.whapi.received || 0) + " received", s.whapi.received ? "" : "off");
    setService("bridge", s.bridge ? "configured" : "not configured", s.bridge ? "" : "off");
    setService("uptime", "live · " + duration(s.uptime_seconds), "");
    expectedOutputs(s.hardware);
  }).catch(function(){
    ["robot","camera","openai","audio","swiggy","whapi","bridge","uptime"].forEach(function(k){
      setService(k, "service offline", "bad");
    });
  }).then(function(){ setTimeout(pollStatus, 2000); });
}

function poll(){
  fetch("/feed?since=" + since, {cache: "no-store"})
    .then(function(r){ return r.json(); })
    .then(function(data){
      setConnected(true);
      var entries = data.entries || [];
      if (entries.length) {
        if (!placeholderGone) {
          feed.innerHTML = "";
          placeholderGone = true;
        }
        var toRender = entries;
        if (firstLoad) toRender = entries.slice(-150); // don't dump a whole day on refresh
        firstLoad = false;
        for (var i = 0; i < toRender.length; i++) {
          feed.appendChild(renderEntry(toRender[i]));
          updateMood(toRender[i]);
        }
        trimFeed();
        if (stick) scrollToBottom();
      }
      since = data.total;
      countEl.textContent = data.total + (data.total === 1 ? " memory" : " memories");
    })
    .catch(function(){ setConnected(false); })
    .then(function(){ setTimeout(poll, 1000); });
}

poll();
pollStatus();

/* ---- cockpit wiring ---- */
var chat = document.getElementById("chat");
var toast = document.getElementById("toast");
var guardOn = false;

function flash(msg){
  toast.textContent = msg;
  toast.style.opacity = 1;
  setTimeout(function(){ toast.style.opacity = 0; }, 2200);
}
function post(path, body){
  return fetch("/api" + path, {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(body || {})})
    .then(function(r){ if (!r.ok) throw new Error(r.status); return r.json(); })
    .catch(function(e){ flash("brain unreachable — is brain.py running?"); throw e; });
}

document.getElementById("send").addEventListener("click", function(){
  var t = chat.value.trim();
  if (!t) return;
  post("/say", {text: t}).then(function(){ chat.value = ""; });
});
chat.addEventListener("keydown", function(ev){
  if (ev.key === "Enter") document.getElementById("send").click();
});
(function(){
  var btn = document.getElementById("listen");
  var pressedAt = 0;
  function down(ev){
    ev.preventDefault();
    pressedAt = Date.now();
    btn.style.filter = "brightness(1.6)";
    post("/listen", {});
    flash("listening — release to send");
  }
  function up(ev){
    ev.preventDefault();
    btn.style.filter = "";
    if (!pressedAt) return;
    var held = Date.now() - pressedAt;
    pressedAt = 0;
    if (held < 400) {  // quick click: 6s window, auto-stop
      flash("listening 6s...");
      setTimeout(function(){ post("/listen_stop", {}); }, 6000);
    } else {
      post("/listen_stop", {});
    }
  }
  btn.addEventListener("mousedown", down);
  btn.addEventListener("touchstart", down);
  btn.addEventListener("mouseup", up);
  btn.addEventListener("mouseleave", function(e){ if (pressedAt) up(e); });
  btn.addEventListener("touchend", up);
})();
document.getElementById("caption").addEventListener("click", function(){
  var t = chat.value.trim();
  if (!t) { flash("type caption text first"); return; }
  post("/command", {c:"text", v:t.slice(0,21)}).then(function(){ chat.value = ""; });
});
document.querySelectorAll(".chip[data-cmd]").forEach(function(el){
  el.addEventListener("click", function(){
    var p = el.getAttribute("data-cmd").split(":");
    post("/command", {c: p[0], v: p[1]});
  });
});
document.querySelectorAll(".chip[data-event]").forEach(function(el){
  el.addEventListener("click", function(){
    var p = el.getAttribute("data-event").split(":");
    post(p[0] === "agent_ask" ? "/ask" : "/event",
         p[0] === "agent_ask" ? {text: p[1]} : {e: p[0], text: p[1]});
  });
});
document.getElementById("ansYes").addEventListener("click", function(){ post("/answer", {answer:"yes"}); });
document.getElementById("ansNo").addEventListener("click", function(){ post("/answer", {answer:"no"}); });
document.getElementById("modeToggle").addEventListener("click", function(){
  post("/mode", {});
  flash("mode toggling — he'll announce it");
});
document.getElementById("reload").addEventListener("click", function(){
  post("/reload", {});
  flash("brain reloading — back in about a minute");
});
document.getElementById("guard").addEventListener("click", function(){
  guardOn = !guardOn;
  this.classList.toggle("on", guardOn);
  post("/guard", {on: guardOn});
});

var cam = document.getElementById("cam");
var camimg = document.getElementById("camimg");
var camTimer = null;
function camStart(){
  // MJPEG stream straight from the brain (:8300) — real ~10fps; <img> is
  // exempt from CORS so no proxy needed. Fallback to polling if it errors.
  camimg.onerror = function(){
    camimg.onerror = null;
    var tick = function(){ camimg.src = "/api/frame?t=" + Date.now(); };
    camimg.onload = function(){ if (!cam.hidden) camTimer = setTimeout(tick, 250); };
    tick();
  };
  camimg.src = "http://" + location.hostname + ":8300/stream";
  // MJPEG streams can die silently (img just freezes) — re-arm every 15s
  setInterval(function(){
    if (!cam.hidden) camimg.src = "http://" + location.hostname + ":8300/stream?r=" + Date.now();
  }, 15000);
}
camStart();  // his eyes are on by default — CAM chip toggles them off
document.getElementById("camToggle").classList.add("on");
document.getElementById("camToggle").addEventListener("click", function(){
  cam.hidden = !cam.hidden;
  this.classList.toggle("on", !cam.hidden);
  if (!cam.hidden && !camTimer) camStart();
  else if (cam.hidden && camTimer) { clearInterval(camTimer); camTimer = null; }
});
})();
</script>
</body>
</html>
"""

# Splice the real face bitmaps in as a JSON object literal — valid JS as-is,
# no escaping needed (base64 is alphanumeric + "/+="). Done once at import.
PAGE = PAGE.replace('"__FACE_DATA_URIS__"', json.dumps(FACE_URIS))


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Bittu dashboard on :{PORT}")
    srv.serve_forever()


def start():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Bittu dashboard on :{PORT}")
    return srv


if __name__ == "__main__":
    main()
