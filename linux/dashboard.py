"""Live view of Bittu's inner life — the demo-table dashboard.

Serves one self-contained page (GET /) that polls GET /feed?since=N for new
journal lines and renders them as a running transcript, styled per entry
kind. Stdlib http.server only — no Flask, no external requests, safe on the
2GB board. Run alongside brain.py:

    JOURNAL=~/bittu-journal.jsonl python3 dashboard.py   (defaults to :8302)

Then open http://<board-ip>:8302 on the laptop/phone next to the robot.
"""
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import journal

PORT = int(os.environ.get("DASHBOARD_PORT", 8302))
BRAIN = os.environ.get("BRAIN_URL", "http://127.0.0.1:8300")  # server.py in brain.py

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
<main id="feed">
  <div class="row k-system placeholder">
    <span class="time"></span><span class="tag">SYSTEM</span>
    <span class="text">waiting for signs of life…</span>
  </div>
</main>
<button id="resume" hidden>new entries ↓</button>

<div id="cam" hidden><span class="camlbl">HIS EYES</span><img id="camimg" alt="camera"></div>
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
document.getElementById("listen").addEventListener("click", function(){
  post("/listen", {});
  flash("listening at the robot — speak now");
});
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
document.getElementById("guard").addEventListener("click", function(){
  guardOn = !guardOn;
  this.classList.toggle("on", guardOn);
  post("/guard", {on: guardOn});
});

var cam = document.getElementById("cam");
var camimg = document.getElementById("camimg");
var camTimer = null;
document.getElementById("camToggle").addEventListener("click", function(){
  cam.hidden = !cam.hidden;
  this.classList.toggle("on", !cam.hidden);
  if (!cam.hidden) {
    var tick = function(){ camimg.src = "/api/frame?t=" + Date.now(); };
    tick(); camTimer = setInterval(tick, 1000);
  } else if (camTimer) { clearInterval(camTimer); camTimer = null; }
});
})();
</script>
</body>
</html>
"""


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Bittu dashboard on :{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
