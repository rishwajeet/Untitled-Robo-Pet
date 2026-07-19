"""Swiggy MCP client — lets Bittu order real food. COD, no payment code.

Token dance (do ONCE on the laptop, near demo time):
  npx mcp-remote https://mcp.swiggy.com/food     # browser opens: phone + OTP
  # token lands in ~/.mcp-auth/... — grep for "access_token", then on the Q:
  export SWIGGY_TOKEN=<access_token>

Raw JSON-RPC over streamable HTTP, no framework — 3 calls: initialize,
tools/list, tools/call. Handles both JSON and SSE-style responses.
"""
import itertools
import json
import os

import requests

BASE = os.environ.get("SWIGGY_MCP", "https://mcp.swiggy.com/food")
TOKEN = os.environ.get("SWIGGY_TOKEN", "")

_ids = itertools.count(1)
_session = {"id": None, "initialized": False}


def _post(payload):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _session["id"]:
        headers["Mcp-Session-Id"] = _session["id"]
    r = requests.post(BASE, json=payload, headers=headers, timeout=30)
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
    return bool(TOKEN)


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
