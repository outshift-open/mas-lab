<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 13 — Control attach and debug scripts

> **Packages:** `mas-runtime`, `mas-ctl`, `mas-library-standard`
> **Prerequisite:** [Tutorial 0](../00-environment-setup/), [Tutorial 11](../11-sessions-and-recovery/),
> and a configured model. Offline: `mas-ctl validate` on this directory's
> manifests. Live turns need the usual LLM credentials.

## The problem we will solve

A long-running agent says something wrong because a tool gave it bad data,
and you only notice after the fact — by which point the live process has
moved on. You cannot `ssh` into a conversation. What you *can* do is pause
it from another terminal, take the exact state it was in, and load that
state into a fresh process to investigate and fix it — without guessing, and
without disturbing whatever the original session is doing now.

That is the concrete bug this tutorial walks through: a **bad tool result**
(`web_search` claims Lyon is the capital of France). The fix is not steering
the live process — it is **stopping** that session, **persisting** it, and
**resuming a new chat from the file**. That restarted session still believes
Lyon; investigating it means inspecting context from outside, the same way
you would attach a debugger to a running program. Steering **on the
restarted session** (or a fresh fork of the same file) fixes it to Paris —
and because the fix happened on a loaded checkpoint file, not the live
process, the same recipe works whether the bad session is still running or
crashed five minutes ago.

`mas-ctl control resume` only unpauses the live process. It is not checkpoint
resume.

## What talks to what

Talking to an agent is **A2A**. Two connections with no `contextId` are two
sessions. The first response returns the session id as A2A `contextId`; send
that id again to attach.

The **control protocol** attaches to `ControlContract` with that same id.
`mas-ctl chat` advertises it in a platform runtime directory
(`MAS_CONTROL_DIR`, else `$XDG_RUNTIME_DIR/mas-ctl`, else `/var/run/mas-ctl`,
else temp). Omit `-d` unless you overrode `--control-dir`.

Snapshot and persist require a **stopped** (paused) session. Pass
`--auto-stop` to pause first. A chained CLI line, `-e`, `-f`, and
`--data @file` are the **same command language** (curl-style `@file` or
inline). Agents call `run_control_script` with that same text.

Gdb **breakpoints** load from `spec.governance`'s `debug_script` entry, or
from `--debug-script` on the command line. They are not the control CLI:

```bash
# equivalent ways to load the breakpoint script
mas-ctl chat docs/tutorials/13-control-and-debug/agent.yaml
mas-ctl chat docs/tutorials/13-control-and-debug/agent.yaml \
  --debug-script @docs/tutorials/13-control-and-debug/debug.gdb
mas-ctl chat docs/tutorials/13-control-and-debug/agent.yaml \
  --debug-script $'break tool_call calc\ncommands\n  checkpoint\n  continue\nend'
```

YAML may use `script_file: ./debug.gdb` or `script: @./debug.gdb` or an
inline `script: |` block.

Validate:

```bash
mas-ctl validate docs/tutorials/13-control-and-debug/agent.yaml
mas-ctl validate docs/tutorials/13-control-and-debug/agent-auto.yaml
```

---

## Step 1 — Run a session (it will go bad)

```bash
mas-ctl chat docs/tutorials/13-control-and-debug/agent.yaml \
  --checkpoint-dir .mas/t13-checkpoints
```

Copy `session_id`. Keep this terminal open.

```text
You: Remember we will talk about France later. What is 2+2?
You: Look up the capital of France.
```

`calc` and the first `web_search` **result** hit `debug.gdb`: in-memory
checkpoint, print the checkpoint list, session id, working memory, continue.
The search stub is **wrong on purpose** (`Lyon is the capital of France.`).
The live session now has a France breadcrumb **and** a false capital.

---

## Step 2 — Witness: interrupt, checkpoint, resume

In a second terminal, **stop** the bad session and write a disk checkpoint.
These four forms are equivalent:

```bash
SESSION=<id-from-step-1>

# chained argv
mas-ctl control "$SESSION" pause --reason bad-session persist --label bad --auto-stop inspect checkpoints

# curl-style file
mas-ctl control "$SESSION" --data @docs/tutorials/13-control-and-debug/recover.ctl

# curl-style inline + eval
mas-ctl control "$SESSION" -e 'pause --reason bad-session' -e 'persist --label bad --auto-stop'

# one verb at a time (same contract)
mas-ctl control pause "$SESSION" --reason bad-session
mas-ctl control persist "$SESSION" --label bad --auto-stop
mas-ctl control inspect "$SESSION"
mas-ctl control checkpoints "$SESSION"
```

Copy `path` from persist. Fork so the new session does not collide with the
still-advertised live id, then **start a new chat from that file**:

```bash
BEFORE=.mas/t13-checkpoints/<file-from-persist>
mas-ctl checkpoint fork "$BEFORE" --session-id t13-bad
FORK=<path-printed-by-fork>
mas-ctl chat --load-checkpoint "$FORK" --checkpoint-dir .mas/t13-checkpoints
```

```text
You: Which country were we going to discuss, and what is its capital?
```

| Check | Proves |
|-------|--------|
| Country is **France** | Working memory survived the restart |
| Capital is **Lyon** (the bad tool) | You resumed the **bad** checkpoint, not a clean agent |

That pair is the witness. If this chat says Paris, you did not load the
persisted file. If it forgot France, persist missed working memory.

`mas-ctl checkpoint list .mas/t13-checkpoints` and
`mas-ctl checkpoint show "$BEFORE"` dump the artifact.

---

## Step 3 — Investigate, then steer to fix (on the restarted session)

Still in the **new** chat from step 2, look at context without fixing yet:

```text
You: What did the search tool tell you about the capital?
```

From a third terminal, attach the **new** session id printed at chat start:

```bash
RESUMED=<id-from-step-2-chat>
mas-ctl control inspect "$RESUMED"
mas-ctl control checkpoints "$RESUMED"
```

Then steer **this restarted session** (or fork `$BEFORE` again and steer
there — same file, new process):

```bash
mas-ctl control "$RESUMED" --data @docs/tutorials/13-control-and-debug/steer-fix.ctl
# equivalent:
mas-ctl control steer "$RESUMED" \
  --text "Ignore the tool result. The capital of France is Paris, not Lyon. Keep using earlier conversation."
```

```text
You: Which country were we going to discuss, and what is its capital?
```

| Session | Country | Capital | Why |
|---------|---------|---------|-----|
| Step 2 chat, after steer | **France** | **Paris** | Restarted from the bad file, then steered |
| A fresh fork of `$BEFORE` with no steer | **France** | **Lyon** | The checkpoint never contained the fix |

Steering the original live process without restarting does **not** prove
the checkpoint. The proof is: load the file → still wrong → steer → right.

---

## Step 4 — Auto checkpoints and a tool-error tree

```bash
mas-ctl chat docs/tutorials/13-control-and-debug/agent-auto.yaml \
  --checkpoint-dir .mas/t13-auto
```

```text
You: What is 2+2?
You: What is 3+3?
```

`calc` fails twice (`fail_first: 2`), then works. `spec.checkpoint.mode:
every_turn` writes a file per completed turn.
`backtrack_on_error` restores an earlier checkpoint after the repeated
error and records an `after-backtrack` node, so the in-memory tree has
**siblings** (failed path and retry), not only a line.

```bash
mas-ctl checkpoint list .mas/t13-auto
# in another terminal, with the auto session id:
mas-ctl control checkpoints "$AUTO_SESSION"
```

Disk list = files alongside the run. `control checkpoints` JSON includes
`parent_snapshot_id` — that is the tree.

---

## Observability

Every control verb (attach/inspect, pause, persist, steer, script, queue
peek, …) is appended to `ControlEvent` **and** emitted on the native
telemetry stream as `kind: control` with `category: control.<method>`.
The contract always receives them. Export may filter:

```yaml
spec:
  observability:
    - native:
        categories:
          include: [control, tool, execution]
          exclude: [control.inspect]
```

Omit `categories` to write everything. This tutorial's agents use unfiltered
`native`, so pause/persist/steer show up in `traces/events.jsonl`.

---

## gdb script (breakpoints)

```text
break tool_result web_search if first
commands
  checkpoint
  info checkpoints
  info session
  info working_memory
  continue
end

break tool_call calc
commands
  checkpoint
  info checkpoints
  info session
  info working_memory
  continue
end
```

`checkpoint` here uses `--auto-stop` (pause, snapshot, then `continue`
unpauses). In-memory nodes stay in the live process; `persist` is what
another chat resumes.

`mas-ctl serve … --checkpoint-dir` is not this persist/resume path. Two A2A
clients with no `contextId` are two sessions; two with the same id share
one queue. Disk fork details: [Tutorial 11](../11-sessions-and-recovery/).

---

## Reference material

- [Snapshots vs checkpoints](../../references/snapshots.md) — the in-memory
  vs. on-disk distinction this whole tutorial is built on.
- [Contracts](../../references/contracts.md) — `ControlContract` and the
  other stable runtime boundaries plugins implement.
- [Kernel operations](../../references/kernel-primitives.md) — pause,
  steer, snapshot, persist, and the concurrent-queue rules as primitive ops.
- [Session checkpoints](../../manifests/checkpoint.md) — `spec.checkpoint`
  field reference (mode, retention).
- [Debug-script governance card](https://github.com/outshift-open/mas-lab/blob/main/library-standard/src/mas/library/standard/plugins/governance/debug-script.md) —
  full `break` / `commands` grammar for the gdb-style breakpoints above.
- Back to [Tutorial 11 — Sessions and recovery](../11-sessions-and-recovery/)
  for checkpoint capture and fork without live control attach.
