# Bittu demo runbook — companion mode into agent mode

Three-minute judging slot. Companion beats first, then "he also has a job" —
Bittu tracks a live Claude Code session and a judge presses a physical
button to approve or deny one of its commands. Read this end to end once
before 4:30, then again as a dry-run with the team.

No emoji anywhere below — this may get printed or shown on the OLED.

---

## Before judges arrive: terminal layout

Run these in order. Confirm each one before moving to the next.

**Terminal 1 (Mac) — the live Claude Code session bridge.py talks to:**
```bash
tmux new -s claude
cd /Users/rishwajeetsingh/Documents/machine_house/Untitled-Robo-Pet/demo/playground
export ROBOT_IP=<board-ip>          # e.g. 192.168.1.42 — from `hostname -I` on the Q
claude --dangerously-skip-permissions
```
The `--dangerously-skip-permissions` flag is not optional — see "Why the
bypass flag" below. The tmux session name must be exactly `claude`;
`laptop/bridge.py` has that name hardcoded as its send-keys target.

The very first time Claude Code opens this folder it shows a one-time
"trust this folder?" prompt (this project's `.claude/settings.json` pre-
approves Read/Edit/Write/Glob/Grep). Press Enter to accept **now**, not
during judging — it needs one real keypress and only appears once per
folder.

**Terminal 2 (Mac) — the bridge:**
```bash
cd /Users/rishwajeetsingh/Documents/machine_house/Untitled-Robo-Pet
python3 laptop/bridge.py
```
Listens on :8400. This is what turns "tell claude to fix the tests" (heard
by Bittu) into a prompt typed into Terminal 1.

**On the robot (Q):**
```bash
export BRIDGE_URL=http://<laptop-ip>:8400
# plus whatever brain.py invocation the team lead settled on (audio, sass, etc.)
python3 brain.py
```
This brings up the :8300 agent-mode server that `hooks/approve.sh` and the
demo's hooks talk to, plus companion mode.

**Second screen (optional but good theater):** browse
`http://<board-ip>:8302` for `linux/dashboard.py`, or `tail -f
~/bittu-journal.jsonl` on the Q so judges can watch the event stream
scroll while Claude works.

**Set the real robot IP in the demo project's hooks** (only needs doing
once per venue network, do it right after Terminal 1/2 above):
```bash
sed -i '' 's/ROBOT_IP_PLACEHOLDER/<board-ip>/g' \
  /Users/rishwajeetsingh/Documents/machine_house/Untitled-Robo-Pet/demo/playground/.claude/settings.json
```
Then restart the Terminal 1 claude session so it picks up the edited
settings.json (settings are read at startup).

**Verify all four hook URLs before judges arrive, not just the approve
one** — this bit me in dry-run testing (see "Findings" below):
```bash
curl -s -m 2 -X POST http://<board-ip>:8300/event -d '{"e":"agent_start","text":"ping"}'
curl -s -m 2 -X POST http://<board-ip>:8300/ask   -d '{"text":"test ask"}'
curl -s http://<board-ip>:8300/answer
```
If the OLED doesn't react to the first curl, the placeholder wasn't fully
replaced somewhere — grep the settings.json for `ROBOT_IP_PLACEHOLDER`
again.

### Pre-demo checklist (do all of this before judges approach)

1. Robot booted, OLED showing a face, WiFi joined.
2. `hostname -I` on the Q — confirm the IP, export it everywhere above.
3. Terminal 1: tmux `claude` session up, folder-trust dialog already
   accepted, sitting at an idle prompt in `demo/playground`.
4. Terminal 2: `bridge.py` running, no errors printed.
5. Robot side: `brain.py` running, `BRIDGE_URL` set.
6. `sed` the ROBOT_IP_PLACEHOLDER in `demo/playground/.claude/settings.json`.
7. Curl-test all three event URLs plus `/ask` + `/answer` (above) — confirm
   the robot visibly reacts each time, not just that curl returns 200.
8. Confirm `demo/playground/game.py` is in its broken starting state:
   `cd demo/playground && python3 run_tests.py` should print `TESTS
   FAILING (2/9 green)` in red. If it prints green, someone already fixed
   it — restore from git or retype the four known bugs (below).
9. Say "Bittu, tell claude to fix the tests" once as a full rehearsal,
   confirm the OLED shows the ask, press the talk button, confirm it goes
   green. Reset game.py to broken again afterward.
10. Phone hotspot ready as a fallback network, laptop and board both
    pre-joined to it (venue WiFi client isolation is the #1 risk — test
    the curl above over venue WiFi specifically, don't assume).

---

## Timeline

### 0:00 — Companion beats

Judge approaches. Let Bittu greet them off the camera (he comments on
something he sees). Then, in order:

- "Pick him up." → protest animation.
- "Now shake him." → dizzy meltdown.
- Pet or tap → forgives, hearts.
- Hold the talk button, ask him anything → sassy answer referencing what
  he sees.
- Optional if time allows: rock-paper-scissors against the camera.

Keep this to about 60-75 seconds. Watch the judge's energy — if they're
already reaching for their phone to check the time, cut straight to the
mode switch.

### 1:15-1:30 — Mode switch: "he also has a job"

Say to the room: **"He also has a job — he's the permission system for my
coding agent right now."** Then speak or type to Bittu:

> **"Tell claude to fix the tests."**

This lands in the tmux `claude` session via the bridge as: *"The test
suite in this project is red. Investigate and fix game.py so python3
run_tests.py is fully green. Do not modify test_game.py."* (that exact
prompt is what was dry-run tested — see Findings; if you say something
different live, expect similar but not identical timing).

**What the robot shows, in order** (this is the real, tested sequence):

1. **UserPromptSubmit fires immediately** — OLED shows "fixing your
   tests" (agent_start). Say out loud: *"He just told Claude to start."*
2. Claude reads the files silently (no robot reaction — Read/Glob calls
   don't hit the hook).
3. **First Bash call → PreToolUse fires** — OLED shows the permission
   ask. **This is the first button moment. Judge presses the talk button
   (YES).** Narrate while it's pending: *"Right now Claude wants to run a
   shell command, and it can't — until Bittu says so."*
4. OLED flips to "claude is working" (agent_working) after each
   Bash/Edit/Write call. Claude edits game.py for the next 15-30 seconds
   — this is the quiet stretch, see "What to say" below.
5. **A later Bash call (the verification test run) → PreToolUse fires
   again — this is the DENY moment. Judge presses the pet button (NO).**
   Claude's response, verified word-for-word in testing: it does **not**
   retry silently. It says something like *"Bittu denied this command...
   that's a deliberate deny, I'm not retrying it behind your back"* and
   stops, asking to be told to continue. This is real, not scripted —
   the deny is a hard block even though the session is running with
   permissions bypassed.
6. **Re-prompt, spoken or typed:** *"Go ahead, run the tests now."* This
   is a required step, not a flourish — Claude will not proceed on its
   own after a deny. New Bash call fires a fresh PreToolUse ask. **Judge
   presses talk (YES) again.**
7. Tests run, all green. **Stop hook fires** — OLED shows "tests green!"
   (agent_done), robot celebrates.

### 2:30 — Payoff

Turn the laptop screen to the judges. `python3 run_tests.py` output ends
in a green banner:
```
==================================================
  ALL TESTS PASSED   (9/9 green)
==================================================
```
Closers to have ready, pick one:
- "Four separate bugs, and one of them — the score display — never
  crashed. It just quietly showed you losing when you'd won. Claude
  caught it because the robot made it explain itself before it could
  even check its own work."
- "That was the AI asking a physical robot for permission to touch code
  — and the robot said no, once, on purpose, and the AI listened."

---

## What to say while Claude works (dead air kills demos)

The fix-and-verify stretch runs roughly 30-55 seconds of actual thinking
plus however long the two button presses take. Fill it, don't narrate the
code:

- "He's not just showing a status light — every one of these OLED faces
  is a real webhook firing off Claude Code's own lifecycle events."
- "Notice he can't just click 'allow' himself. A physical human has to
  press that button. That's the whole point."
- While the deny is pending: "Watch what happens if I press the wrong
  button here" (then press pet/NO) — "...and now the AI has to ask
  again. It doesn't get to just try a different approach and sneak past
  him."
- If it's taking longer than expected: ask Bittu an unrelated voice
  question (weather, a joke) to bridge the gap — companion mode still
  works while the agent thinks in the background, they're not mutually
  exclusive.

---

## Top 3 failure modes and recovery

1. **Venue WiFi drops mid-demo (laptop can't reach the board).**
   Recovery: the companion beats (camera greet, pick-up protest, pet
   reaction) are all MCU-local reflexes — they keep working with zero
   network. Fall back to those beats and skip the mode switch, or cut to
   the phone hotspot (should already be pre-joined per the checklist).
   Bash commands do NOT hang forever if the robot vanishes mid-agent-run:
   `approve.sh` polls for 20 seconds then fails open (exits 0, allows the
   command) — so a dead robot slows the demo, it doesn't brick it. Say
   "he's thinking it over" during that 20-second gap if it happens live.

2. **Claude takes noticeably longer than rehearsed (over ~90s with no
   button prompt appearing).** Recovery: say the interrupt line to Bittu
   ("stop him") — this sends Escape to the tmux session via the bridge.
   Then re-issue the same fix prompt; the four bugs are simple enough
   that a second attempt reliably lands fast (the re-prompt in testing
   took about 10 seconds). Don't let a stalled first attempt eat the
   whole slot.

3. **The permission ask never appears (judge never gets a button
   moment).** Two possible causes, different fixes. (a) If Claude just
   plows ahead and finishes with no visible ask at all, the session was
   probably NOT launched with `--dangerously-skip-permissions` and got
   its own separate interactive "requires approval" prompt that nobody
   answered — check Terminal 1's screen, someone may need to press Yes
   there once, then relaunch claude properly before the next attempt.
   (b) If the ask fires on the robot but the buttons don't seem to do
   anything, check `ROBOT_IP` is actually exported in Terminal 1 (not
   just baked into settings.json) — `approve.sh` reads it from the
   environment, and a missing env var makes every ask silently fail-open
   after a 20s poll, which looks like "nothing happened" rather than an
   error.

---

## Findings from dry-run testing (mock robot on :8300, no hardware)

Tested with a throwaway logging HTTP server standing in for the robot,
running the exact hooks config in `demo/playground/.claude/settings.json`
against a real interactive `claude` session in tmux, driven the same way
`bridge.py` drives it (tmux send-keys). Four full runs, playground reset
to the broken 4-bug state before each.

| Run | Setup | Bash calls (asks) | Result | Duration |
|---|---|---|---|---|
| 1 | 3-bug version, all approved | 3 | 8/8 green | ~30s |
| 2 | 4-bug version, all approved | 3 | 9/9 green | ~37s |
| 3 | 4-bug version, all approved | 3 | 9/9 green | ~53s |
| 4 | 4-bug version, 2nd ask denied, then re-prompted | 3 + 1 re-prompt | 9/9 green (two turns) | ~50s to the deny-and-stop, +~10s after re-prompt |

**Spread and what it means for pacing:** the raw agent-only fix time
across approve-only runs was 30-53 seconds — reliably under the 60-120s
window the task was tuned for, because Opus at high reasoning effort
fixes these particular bugs fast. That's fine, not a problem to solve
further: the two live button presses and the deny-then-reprompt beat add
real human-reaction seconds on top of the raw number that no unattended
test can measure (a person, not an instant auto-approve mock, has to
notice the ask, decide, and press), and the choreography above already
budgets narration to cover whatever gap remains. Making the coding task
itself harder to force a bigger number would trade away reliability for
a cosmetic timing match — worse trade for a live demo.

**Verified, not assumed:**
- `hooks/approve.sh`'s bare `exit 0` / `exit 2` (no JSON decision printed)
  does NOT suppress Claude Code's own interactive Bash permission prompt
  by itself — without `--dangerously-skip-permissions`, a real "This
  command requires approval / Yes / Yes and don't ask again / No" prompt
  still appeared on the laptop screen after the hook had already fired.
  The bypass flag is what makes the robot the *only* gate.
- Under `--dangerously-skip-permissions`, an `exit 2` from the PreToolUse
  hook still hard-blocks the Bash call. This is the load-bearing safety
  property for the whole pitch and it held up in testing.
- Claude does not silently retry after a deny. It stops and narrates the
  denial, then waits for a new prompt — confirmed word-for-word in a real
  transcript. The runbook's re-prompt step above is required, not
  decorative.
- Opening `claude` in a brand-new project folder for the first time shows
  a one-time trust-this-folder dialog (triggered here by the
  `permissions.allow` block in settings.json) that needs one keypress.
  Must happen during setup.
- Event hooks (UserPromptSubmit/PostToolUse/Stop) use
  `curl ... &` backgrounded with output suppressed — if the ROBOT_IP
  substitution is missed in even one of the three URLs, that specific
  event silently never reaches the robot (DNS failure on a backgrounded,
  redirected command produces no visible error anywhere). The PreToolUse
  ask/answer path is separately driven by the `ROBOT_IP` environment
  variable via `approve.sh` and can keep working fine even if the event
  URLs are broken — meaning the demo can look 90% correct (permission
  asks work) while the idle/celebrate faces never show. Test all three
  event URLs individually, not just the ask/answer round trip.
- After a turn ends, Claude Code sometimes shows a greyed-out suggested
  next message sitting in the prompt box (e.g. "commit this"). This is
  only a suggestion, not typed or queued input — it will not submit
  unless someone actually presses Enter on it. Don't mistake it for a
  stuck prompt.

---

## The playground's four bugs (for reference, don't peek during the demo)

`game.py` ships broken in four independent, non-overlapping ways so a
partial fix still shows visible progress:

1. `robot_move`: `MOVES[round_num % len(MOVES) + 1]` — off-by-one, throws
   `IndexError` on every third round.
2. `decide_winner`: checks `BEATS[robot] == player` instead of
   `BEATS[player] == robot` — inverts every non-tie result.
3. `Score.record`: writes to `self.score` which doesn't exist (`__init__`
   defines `self.wins`) — `AttributeError` on the first recorded round.
4. `Score.scoreboard`: prints the robot's count in the "YOU" slot and
   vice versa — never crashes, just silently shows the wrong winner. This
   one only becomes visible once bug 3 is fixed (it's masked by the
   crash), which is why a couple of test runs are sometimes needed rather
   than one.

Run `python3 run_tests.py` from `demo/playground/` to confirm the current
state at any time — red banner means broken, green means fixed.
