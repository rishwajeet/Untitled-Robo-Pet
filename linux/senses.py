"""Bittu's senses: device discovery + "who is this."

Written against a Mac where camera index 0 is always the webcam and
`arecord` doesn't exist. The UNO Q (Qualcomm QRB2210) breaks both
assumptions: the SoC exposes its OWN ISP /dev/video* nodes that open() fine
but never yield a real frame, and the mic lives on a USB audio card that
has to be found via `arecord -l`, not guessed.

Also owns person identification -- two tiers, picked automatically:
  A) cv2.face LBPH -- offline, needs opencv-contrib (cv2.face). Fast, no
     network, but almost certainly ABSENT on the board: the pinned
     opencv-python-headless==4.9.0.80 (see requirements.txt) is the
     non-contrib build, so cv2.face won't exist there either.
  B) semantic fallback via gpt-4o-mini vision -- works on plain
     opencv-python-headless (the likely board reality). No biometric
     permanence, but a stored 6-word description + a match call survives a
     6-hour demo where nobody changes clothes, and degrades to "stranger"
     gracefully if OPENAI_API_KEY or network is missing.

Zero-ceremony enrollment: voice.py detects an [[ENROLL:Name]] tag the
model emits when a human introduces themselves and calls strip_enroll_tag()
on every reply -- that both cleans the tag out before speaking AND fires
enroll() against the last face this module saw.
"""
import glob
import json
import os
import platform
import re
import subprocess
import time

import cv2
import numpy as np

import journal

FACES_DIR = os.environ.get("BITTU_FACES_DIR", os.path.expanduser("~/bittu-faces"))
PEOPLE_PATH = os.environ.get("BITTU_PEOPLE", os.path.expanduser("~/bittu-people.json"))
FACE_SIZE = (200, 200)          # common size LBPH trains/predicts on
LBPH_CONFIDENCE_MAX = 80.0      # LBPH confidence is a DISTANCE -- lower is a better match

_ENROLL_RE = re.compile(r"\[\[ENROLL:([^\]]+)\]\]")

_latest_jpeg = None                          # dashboard: newest frame, any grab
_latest_face = {"gray": None, "jpeg": None}   # newest IDENTIFIED face, for enroll()
_seen_counts = {}                             # name -> times recognized this run


# ---------------- latest-frame access (for the dashboard) ----------------

def note_jpeg(jpeg: bytes | None) -> None:
    global _latest_jpeg
    if jpeg:
        _latest_jpeg = jpeg


def get_latest_jpeg() -> bytes | None:
    return _latest_jpeg


def get_latest_face():
    """(gray_crop, full_frame_jpeg) of the last face identify_person() saw."""
    return _latest_face["gray"], _latest_face["jpeg"]


# ---------------- dedicated capture thread ----------------
# The camera must never wait on the brain: while think()/TTS block the main
# loop for seconds, this thread keeps reading frames so the dashboard stream
# stays live and every consumer gets a FRESH frame, not a pre-thought relic.

_latest_frame = None  # newest raw BGR frame (ndarray); capture thread owns cap


def start_capture(cap, fps=10):
    import threading

    def _loop():
        global _latest_frame
        interval = 1.0 / fps
        while True:
            ok, frame = cap.read()
            if ok:
                _latest_frame = frame
                ok2, buf = cv2.imencode(".jpg", frame,
                                        [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok2:
                    note_jpeg(buf.tobytes())
            else:
                time.sleep(0.5)  # camera hiccup — don't spin
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True).start()


def get_latest_frame():
    return _latest_frame


# ---------------- device discovery ----------------

_avf_cache = None  # (video:[(idx,name)], audio:[(idx,name)]) -- one ffmpeg spawn, cached


def _avfoundation_devices():
    """MAC ONLY: enumerate AVFoundation video/audio devices via ffmpeg's
    `-list_devices` probe (same enumeration cv2's AVFoundation backend and
    ffmpeg's avfoundation input use). Cached after the first call."""
    global _avf_cache
    if _avf_cache is not None:
        return _avf_cache
    video, audio = [], []
    try:
        out = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=8).stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _avf_cache = (video, audio)
        return _avf_cache
    section = None
    for line in out.splitlines():
        if "AVFoundation video devices" in line:
            section = video
            continue
        if "AVFoundation audio devices" in line:
            section = audio
            continue
        m = re.search(r"\[(\d+)\]\s+(.+?)\s*$", line)
        if m and section is not None:
            section.append((int(m.group(1)), m.group(2).strip()))
    _avf_cache = (video, audio)
    return _avf_cache


def find_camera():
    """cv2.VideoCapture-openable index/path for the C270, verified by an
    ACTUAL frame read -- isOpened() alone lies on the Q (its own ISP nodes
    open fine but return nothing or tiny/blank frames).

    CAMERA_INDEX env overrides everything — field lesson (2026-07-19):
    ffmpeg's avfoundation device order does NOT match cv2's on macOS
    (ffmpeg said C270=3; cv2 index 3 was a Sony virtual cam's idle card).
    """
    forced = os.environ.get("CAMERA_INDEX")
    if forced is not None:
        journal.log("system", f"camera: CAMERA_INDEX override -> {forced}")
        return int(forced)

    # Mac: prefer the C270 by NAME via ffmpeg's avfoundation list; fall back
    # to built-in (index 0). NOTE: ffmpeg's index is a HINT, not truth — see
    # CAMERA_INDEX note above; set the env when they disagree.
    if platform.system() == "Darwin":
        video, _ = _avfoundation_devices()
        for idx, name in video:
            if re.search(r"c270|logitech", name, re.I):
                journal.log("system", f"camera: C270 found on Mac -> index {idx} ({name})")
                return idx
        journal.log("system", "camera: no C270 on this Mac -> index 0 (built-in)")
        return 0

    candidates = []
    for p in sorted(glob.glob("/dev/v4l/by-id/*")):
        if re.search(r"c270|logitech", p, re.I):
            candidates.append(p)
    for name_path in sorted(glob.glob("/sys/class/video4linux/video*/name")):
        try:
            name = open(name_path).read().strip()
        except OSError:
            continue
        if re.search(r"c270|logitech", name, re.I):
            m = re.search(r"video(\d+)", name_path)
            if m:
                candidates.append(f"/dev/video{m.group(1)}")
    candidates += list(range(10))  # blind fallback, frame-verified below

    tried = set()
    for cand in candidates:
        if cand in tried:
            continue
        tried.add(cand)
        cap = cv2.VideoCapture(cand)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        cap.release()
        if ok and _frame_looks_real(frame):
            journal.log("system", f"camera: picked {cand}")
            return cand
    journal.log("system", "camera: nothing verified, falling back to 0")
    return 0


def _frame_looks_real(frame) -> bool:
    """Rejects the Q ISP's metadata/blank nodes: too small, or a flat
    (all-one-value) image -- a real webcam frame has texture."""
    if frame is None or frame.size == 0:
        return False
    h, w = frame.shape[:2]
    if h < 120 or w < 160:
        return False
    return float(np.std(frame)) > 1.0


def find_mic() -> str:
    """Linux: arecord device string for the C270 mic, parsed from `arecord -l`.

    MAC: an ffmpeg avfoundation AUDIO DEVICE INDEX (as a string) -- prefers
    the C270's own mic by name when it's plugged into the Mac, else the
    built-in mic (MacBook/Mac mini mic), else avfoundation index 0."""
    if platform.system() == "Darwin":
        _, audio = _avfoundation_devices()
        for idx, name in audio:
            if re.search(r"c270|logitech", name, re.I):
                journal.log("system", f"mic: C270 found on Mac -> avfoundation index {idx} ({name})")
                return str(idx)
        for idx, name in audio:
            if re.search(r"macbook|built-?in|mac\s*mini|mac\s*studio", name, re.I):
                journal.log("system", f"mic: no C270, using built-in -> index {idx} ({name})")
                return str(idx)
        idx = audio[0][0] if audio else 0
        journal.log("system", f"mic: no C270/built-in match, using avfoundation index {idx}")
        return str(idx)
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True,
                              timeout=5, check=True).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired,
             subprocess.CalledProcessError) as e:
        journal.log("system", f"mic: arecord -l failed ({e}), using default")
        return "default"

    cards = re.findall(r"^card (\d+):\s*\S+\s*\[([^\]]*)\].*?device (\d+):",
                        out, re.M)
    for card, desc, dev in cards:          # tier 1: exact C270/Logitech match
        if re.search(r"c270|logitech", desc, re.I):
            device = f"plughw:{card},{dev}"
            journal.log("system", f"mic: picked {device} ({desc})")
            return device
    for card, desc, dev in cards:           # tier 2: any USB capture card
        if re.search(r"usb", desc, re.I):
            device = f"plughw:{card},{dev}"
            journal.log("system", f"mic: no exact match, using {device} ({desc})")
            return device
    journal.log("system", "mic: no USB capture device found, using default")
    return "default"


# ---------------- person identification ----------------

def _has_lbph() -> bool:
    return hasattr(cv2, "face") and hasattr(cv2.face, "LBPHFaceRecognizer_create")


def report_identification_tier() -> str:
    tier = "LBPH (cv2.face, offline)" if _has_lbph() else "semantic (gpt-4o-mini vision)"
    journal.log("system", f"person ID tier: {tier}")
    return tier


def _ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def identify_person(frame_bgr, cascade) -> dict | None:
    """One face -> {"name", "known", "times_seen"}. None if no face visible.
    Journals every identification (kind="seen") and remembers the crop/jpeg
    for a later enroll() call."""
    if cascade is None or frame_bgr is None:
        return None
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])  # largest/closest face
    crop = cv2.resize(gray[y:y + h, x:x + w], FACE_SIZE)
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
    jpeg = buf.tobytes() if ok else None
    _latest_face["gray"], _latest_face["jpeg"] = crop, jpeg

    if _has_lbph():
        name = _lbph_state().identify(crop)
        if name:
            n = _seen_counts[name] = _seen_counts.get(name, 0) + 1
            journal.log("seen", f"{name} ({_ordinal(n)} time today)")
            return {"name": name, "known": True, "times_seen": n}
        journal.log("seen", "stranger")
        return {"name": "stranger", "known": False, "times_seen": 0}

    if jpeg is None:
        return {"name": "stranger", "known": False, "times_seen": 0}
    name, known, n = _people_state().identify(jpeg)
    if known:
        journal.log("seen", f"{name} ({_ordinal(n)} time today)")
    else:
        journal.log("seen", f"new face ({name})")
    return {"name": name, "known": known, "times_seen": n}


def enroll(name: str) -> None:
    """Zero-ceremony enrollment: called when the human says their name
    mid-conversation. Uses the last face identify_person() saw -- no crop
    needs to be threaded through voice.py's tool-call plumbing."""
    name = (name or "").strip()
    if not name:
        return
    gray, jpeg = get_latest_face()
    if _has_lbph():
        if gray is not None:
            _lbph_state().enroll(name, gray)
    else:
        _people_state().enroll(name, jpeg)
    journal.log("system", f"enrolled: {name}")


def strip_enroll_tag(text: str) -> str:
    """Strip a trailing [[ENROLL:Name]] tag from a model reply, enrolling
    that name as a side effect. Call on every voice.think() reply -- safe
    (no-op) when no tag is present."""
    m = _ENROLL_RE.search(text or "")
    if not m:
        return text
    enroll(m.group(1))
    return _ENROLL_RE.sub("", text).strip()


# ---- tier A: LBPH (cv2.face) ----

_lbph_singleton = None


def _lbph_state():
    global _lbph_singleton
    if _lbph_singleton is None:
        _lbph_singleton = _LBPH()
    return _lbph_singleton


class _LBPH:
    def __init__(self):
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.labels = {}  # int label -> name
        self._train()

    def _train(self):
        faces, labels = [], []
        os.makedirs(FACES_DIR, exist_ok=True)
        for i, name in enumerate(sorted(os.listdir(FACES_DIR))):
            person_dir = os.path.join(FACES_DIR, name)
            if not os.path.isdir(person_dir):
                continue
            self.labels[i] = name
            for fp in glob.glob(os.path.join(person_dir, "*.png")):
                img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    faces.append(cv2.resize(img, FACE_SIZE))
                    labels.append(i)
        if faces:
            self.recognizer.train(faces, np.array(labels))
            journal.log("system",
                        f"LBPH trained: {len(faces)} faces, {len(self.labels)} people")
        else:
            journal.log("system", "LBPH: no enrolled faces yet")

    def identify(self, gray_face) -> str | None:
        if not self.labels:
            return None
        try:
            label, confidence = self.recognizer.predict(gray_face)
        except cv2.error:
            return None
        if confidence <= LBPH_CONFIDENCE_MAX:
            return self.labels.get(label)
        return None

    def enroll(self, name: str, gray_face) -> None:
        person_dir = os.path.join(FACES_DIR, name)
        os.makedirs(person_dir, exist_ok=True)
        cv2.imwrite(os.path.join(person_dir, f"{int(time.time())}.png"), gray_face)
        self._train()  # cheap enough for a handful of people at demo scale


# ---- tier B: semantic (gpt-4o-mini vision) ----

_semantic_singleton = None


def _people_state():
    global _semantic_singleton
    if _semantic_singleton is None:
        _semantic_singleton = _Semantic()
    return _semantic_singleton


def _load_people() -> dict:
    try:
        with open(PEOPLE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_people(people: dict) -> None:
    with open(PEOPLE_PATH, "w") as f:
        json.dump(people, f, indent=2)


class _Semantic:
    """people.json: {name_or_auto_label: {description, first_seen, times_seen}}"""

    def __init__(self):
        self.people = _load_people()
        self._pending_label = None  # last auto-labeled stranger, for enroll() to claim

    def identify(self, jpeg_bytes: bytes) -> tuple[str, bool, int]:
        """Always returns something. A brand-new face gets an auto-label +
        6-word description stored immediately -- no waiting for a spoken
        name. Never raises: any failure degrades to ("stranger", False, 0)."""
        import base64
        descs = "\n".join(f"- {n}: {p.get('description', '')}"
                           for n, p in self.people.items()) or "(nobody yet)"
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or "sk-missing")
            b64 = base64.b64encode(jpeg_bytes).decode()
            r = client.chat.completions.create(
                model="gpt-4o-mini", max_tokens=30,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text":
                     f"Known people:\n{descs}\n\nDoes this photo match one of "
                     "them? Reply with EXACTLY their name if so. If it's "
                     "nobody on the list, reply 'NEW: ' followed by a 6-word "
                     "visual description (clothing/hair/accessories)."},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                                   "detail": "low"}}]}])
            answer = (r.choices[0].message.content or "").strip()
        except Exception as e:
            journal.log("system", f"semantic ID failed: {e}")
            return "stranger", False, 0

        if answer.upper().startswith("NEW"):
            desc = answer.split(":", 1)[1].strip() if ":" in answer else answer
            label = f"person{len(self.people) + 1}"
            self.people[label] = {"description": desc,
                                   "first_seen": time.strftime("%H:%M:%S"),
                                   "times_seen": 1}
            _save_people(self.people)
            self._pending_label = label
            return label, False, 1

        if answer in self.people:
            self.people[answer]["times_seen"] = self.people[answer].get("times_seen", 0) + 1
            _save_people(self.people)
            self._pending_label = None
            return answer, True, self.people[answer]["times_seen"]

        return "stranger", False, 0  # model answered off-list -- don't crash the demo

    def enroll(self, name: str, jpeg_bytes: bytes | None = None) -> None:
        if self._pending_label and self._pending_label in self.people:
            self.people[name] = self.people.pop(self._pending_label)
        else:
            entry = self.people.get(name, {"description": "", "times_seen": 0,
                                            "first_seen": time.strftime("%H:%M:%S")})
            entry["times_seen"] = entry.get("times_seen", 0) + 1
            self.people[name] = entry
        self._pending_label = None
        _save_people(self.people)
