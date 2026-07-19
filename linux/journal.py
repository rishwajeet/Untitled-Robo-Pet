"""The one place where all interactions live.

Every sense, word, mood, agent event, and tool call appends here — heartbeat
reads it back so Bittu is one continuous being across modes, not two apps.
Append-only jsonl; survives restarts; greppable at the demo table.
"""
import json
import os
import time

PATH = os.environ.get("JOURNAL", os.path.expanduser("~/bittu-journal.jsonl"))


def log(kind: str, text: str, **meta):
    entry = {"t": time.strftime("%H:%M:%S"), "kind": kind, "text": text}
    entry.update(meta)
    with open(PATH, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def recent(n: int = 18) -> str:
    """Last n entries as compact lines for prompt context."""
    try:
        with open(PATH) as f:
            lines = f.readlines()[-n:]
    except FileNotFoundError:
        return "(nothing yet — just woke up for the first time)"
    out = []
    for ln in lines:
        try:
            e = json.loads(ln)
            out.append(f"{e['t']} [{e['kind']}] {e['text']}")
        except json.JSONDecodeError:
            pass
    return "\n".join(out) or "(empty)"
