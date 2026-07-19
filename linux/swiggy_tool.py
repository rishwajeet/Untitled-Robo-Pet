"""Swiggy MCP client — lets Bittu order real food. COD, no payment code.

For local development, open http://localhost:8300/swiggy/auth. The robot's
HTTP server runs OAuth 2.1 + PKCE and keeps the five-day token only in memory.
SWIGGY_TOKEN remains available as a non-interactive override.

Raw JSON-RPC over streamable HTTP, no framework — 3 calls: initialize,
tools/list, tools/call. Handles both JSON and SSE-style responses.
"""
import base64
import hashlib
import itertools
import json
import os
import secrets
import threading
import time
from urllib.parse import urlencode

import requests

BASE = os.environ.get("SWIGGY_MCP", "https://mcp.swiggy.com/food")
OAUTH_BASE = os.environ.get("SWIGGY_OAUTH_BASE", "https://mcp.swiggy.com")
CALLBACK = os.environ.get("SWIGGY_REDIRECT_URI", "http://localhost:8300/swiggy/callback")

_ids = itertools.count(1)
_session = {"id": None, "initialized": False}
_auth = {
    "access_token": os.environ.get("SWIGGY_TOKEN", ""),
    "expires_at": None,
    "client_id": None,
    "state": None,
    "verifier": None,
}
_auth_lock = threading.Lock()


_TOKEN_FILE = os.path.expanduser("~/.bittu-swiggy-token.json")


def _load_saved_token():
    """Survive brain restarts: reload the OAuth token from disk if fresh."""
    try:
        import json as _json
        with open(_TOKEN_FILE) as f:
            saved = _json.load(f)
        if saved.get("expires_at", 0) > time.time() + 60 and saved.get("access_token"):
            _auth["access_token"] = saved["access_token"]
            _auth["expires_at"] = saved["expires_at"]
    except (OSError, ValueError):
        pass


def _save_token():
    try:
        import json as _json
        with open(_TOKEN_FILE, "w") as f:
            _json.dump({"access_token": _auth["access_token"],
                        "expires_at": _auth["expires_at"]}, f)
        os.chmod(_TOKEN_FILE, 0o600)
    except OSError:
        pass


_load_saved_token()


def _token():
    with _auth_lock:
        if _auth["expires_at"] and time.time() >= _auth["expires_at"] - 60:
            _auth["access_token"] = ""
        return _auth["access_token"]


def begin_auth() -> str:
    """Register a localhost OAuth client and return Swiggy's consent URL."""
    registration = requests.post(f"{OAUTH_BASE}/auth/register", json={
        "client_name": "Bittu local hackathon server",
        "redirect_uris": [CALLBACK],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }, timeout=15)
    registration.raise_for_status()
    client_id = registration.json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    with _auth_lock:
        _auth.update(client_id=client_id, state=state, verifier=verifier)
    params = {
        'response_type': 'code', 'client_id': client_id,
        'redirect_uri': CALLBACK, 'code_challenge': challenge,
        'code_challenge_method': 'S256', 'state': state, 'scope': 'mcp:tools',
    }
    return f"{OAUTH_BASE}/auth/authorize?{urlencode(params)}"


def finish_auth(code: str, state: str):
    """Exchange the localhost callback code and retain the token in memory."""
    with _auth_lock:
        if not state or not secrets.compare_digest(state, _auth["state"] or ""):
            raise ValueError("invalid OAuth state")
        verifier = _auth["verifier"]
    response = requests.post(f"{OAUTH_BASE}/auth/token", json={
        "grant_type": "authorization_code", "code": code,
        "code_verifier": verifier, "redirect_uri": CALLBACK,
    }, timeout=15)
    response.raise_for_status()
    token = response.json()
    with _auth_lock:
        _auth["access_token"] = token["access_token"]
        _auth["expires_at"] = time.time() + int(token.get("expires_in", 432000))
        _save_token()
        _auth["state"] = _auth["verifier"] = None
    reset_session()


def reset_session():
    _session.update(id=None, initialized=False)


def auth_status() -> dict:
    token = _token()
    with _auth_lock:
        return {"authenticated": bool(token), "expires_at": _auth["expires_at"]}


def _post(payload):
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _session["id"]:
        headers["Mcp-Session-Id"] = _session["id"]
    r = requests.post(BASE, json=payload, headers=headers, timeout=30)
    if r.status_code in (401, 419):
        with _auth_lock:
            _auth["access_token"] = ""
        reset_session()
        raise RuntimeError("Swiggy login expired; open /swiggy/auth again")
    r.raise_for_status()
    if sid := r.headers.get("Mcp-Session-Id"):
        _session["id"] = sid
    text = r.text
    if "text/event-stream" in r.headers.get("Content-Type", ""):
        for line in text.splitlines():  # take last data: line = the result
            if line.startswith("data:"):
                text = line[5:].strip()
    return json.loads(text) if text.strip() else {}


def _rpc(method, params=None):
    resp = _post({"jsonrpc": "2.0", "id": next(_ids),
                  "method": method, "params": params or {}})
    if "error" in resp:
        return {"error": resp["error"].get("message", "mcp error")}
    return resp.get("result", {})


def _ensure_init():
    if _session["initialized"]:
        return
    _rpc("initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "bittu", "version": "1.0"},
    })
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    _session["initialized"] = True


def available() -> bool:
    return bool(_token())


def openai_tools() -> list:
    """Swiggy MCP tools formatted for OpenAI function calling."""
    _ensure_init()
    out = []
    for t in _rpc("tools/list").get("tools", []):
        out.append({"type": "function", "function": {
            "name": t["name"],
            "description": (t.get("description") or t["name"])[:1000],
            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
        }})
    return out


def call(name: str, arguments: dict) -> str:
    _ensure_init()
    result = _rpc("tools/call", {"name": name, "arguments": arguments})
    if "error" in result:
        return json.dumps(result)
    parts = result.get("content", [])
    texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    return ("\n".join(texts) or json.dumps(result))[:4000]  # keep context lean
