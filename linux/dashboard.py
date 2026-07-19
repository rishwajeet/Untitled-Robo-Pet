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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import journal

PORT = int(os.environ.get("DASHBOARD_PORT", 8302))

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

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == "/":
            self._html(200, PAGE)
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
  position:fixed; left:50%; bottom:18px; transform:translateX(-50%);
  padding:8px 16px; border-radius:999px; border:1px solid var(--line);
  background:rgba(17,20,32,.92); color:var(--teal); font-size:12px; font-weight:700;
  letter-spacing:.03em; cursor:pointer; box-shadow:0 6px 20px rgba(0,0,0,.35);
}
#resume[hidden]{display:none;}
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
