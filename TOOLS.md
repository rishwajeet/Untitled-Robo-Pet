# Adding tools/MCPs to Bittu — the contract

Bittu's brain runs ONE tool loop (`voice.py: think(..., tools=True)`).
Everything the robot can DO by voice goes through it. Two ways in:

## Already exists — do not rebuild

| Tool | Where | Status |
|---|---|---|
| weather (Open-Meteo, no key) | `tools_local.py` | working |
| lookup (Wikipedia) | `tools_local.py` | working |
| time, rock-paper-scissors, guard mode | `tools_local.py` | working |
| Claude Code bridge (prompt/interrupt) | `tools_local.py` | verified |
| Swiggy MCP client (food/IM/dineout) | `swiggy_tool.py` | written; needs OTP token → see README |

## Path A — simple tool (an API you can curl): 10 lines in tools_local.py

1. Write the function: takes ONE string arg, returns a string result.
   (`tools_local.call()` passes only the first argument value — one param max,
   or extend call() first if you truly need two.)
2. Register it in `openai_tools()` with `_tool("name", "description", "param")`.
   The DESCRIPTION is what makes the model pick it — write it like you're
   telling Bittu when to use it.
3. Add it to `DISPATCH`.
4. Test in isolation:
   `python3 -c "import tools_local; print(tools_local.yourfn('test input'))"`
5. Optionally add a routing hint to PERSONALITY in voice.py ("if the human
   asks you to X, use the yourfn tool").

## Path B — a real MCP server (like WhatsApp): copy swiggy_tool.py

`swiggy_tool.py` is a complete raw MCP client (~90 lines): initialize →
tools/list → tools/call over JSON-RPC HTTP, Bearer auth, handles SSE
responses. For another MCP server:

1. `cp swiggy_tool.py whatsapp_tool.py`; change BASE (server URL) and the
   token env var name.
2. In `voice.py think()`, merge its tools exactly like swiggy:
   `if whatsapp_tool.available(): tool_defs += whatsapp_tool.openai_tools()`
   and route its names in the dispatch branch (match by name-in-set, same
   as `local_names`).
3. Test in isolation BEFORE wiring into the robot:
   `TOKEN=... python3 -c "import whatsapp_tool as w; print(w.openai_tools()[:2])"`
   If tools list, you're live. If auth is OAuth-with-browser, do the token
   dance via `npx mcp-remote <server-url>` and steal the access_token from
   `~/.mcp-auth/` (that's the Swiggy recipe, README "Swiggy MCP" section).

## Rules that keep the demo alive

- Tool results come back to the model — keep them SHORT (truncate at ~4000
  chars like swiggy does). A giant result = 30s of silence at the demo table.
- Every tool must fail as a STRING ("whatsapp unreachable: timeout"), never
  an exception — Bittu turns failures into in-character grumbling.
- One honest tool beats five vaporware ones. If it can't demo a REAL
  side effect (actual message sent, actual order placed), cut it.
- After adding a tool, add one line to the demo runbook (demo/) with the
  voice phrase that triggers it.
