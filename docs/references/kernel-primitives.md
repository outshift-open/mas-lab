<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Kernel operations

The runtime exposes a small set of operations. Subagents, recovery, and
debug are combinations of those operations, not separate engines.

## Operations

| Operation | Meaning |
| --- | --- |
| Start / stop | Materialize a spec into a running agent; tear it down |
| Step | Current state + input → next state, through governance, written to the trace |
| Spawn | Start a child agent with a parent id |
| Snapshot | Cheap in-memory picture of the run (kernel, working memory, spec revision) |
| Persist | Write that picture to disk |
| Navigate | Move a debug cursor on the snapshot tree; does not change the live run until promote |
| Pause / resume / steer / undo | Control. Pause blocks the next user turn |
| Spec revision | Recorded change to the live spec (disable a tool, switch a pattern) |

Plugin code, an LLM tool advertisement, and an admin caller (`ControlContract`)
call the same functions. Multi-host attach is a library `control_protocol`
plugin (JSON-lines unix/TCP). A2A is how people talk to an agent. Two A2A
connections with no `contextId` are two sessions. The first response returns
the session id as A2A `contextId`; a later connection that sends that id
attaches to the same session. Concurrent attachers share one `TurnInputQueue`.

Inbound user turns are a subset of `ControlContract`: A2A `message/send` is
`send_message` (queue a turn at the tail). A2A has no steer RPC. `steer` is
control-protocol only. `AgentCommContract.send` is outbound peer send after
delegation, not inbound user input. `UserIOContract` is progress egress.
`input-required` is HITL, not a splice.

## Concurrent queue

All queue mutations are lock-linearized per session:

| Verb | Concurrent rule |
| --- | --- |
| `send_message` | A2A **Send Message** (`message/send`). Always succeeds. Tail only, `action="turn"`. Additional input on a non-terminal working task waits in the queue. Never preempts. |
| `enqueue_input` | Control-protocol queue mutation. Default `at="tail"`; `at="head"` or `at=<index>` from `inspect_queue` (`[0, len]`). May set `action="steer"` for a later cycle. Never conflicts. |
| `cancel_queued` / drop | CAS on `revision`. Gone id → `QueueItemGone`. |
| `reorder_queue` / move | CAS on `revision`. Must list every live id once. |
| `set_queued_action` (queue → steer) | CAS on `revision`. Changes a still-queued item. |
| `steer` (`preempt`) | Keep streamed tokens, stop the rest of this decode, continue. The decode is preempted — not a finished client response. Unavailable on A2A. |
| `steer` (`replace`) | Discard streamed tokens, stop this decode, start a new exclusive turn. Unavailable on A2A. |
| `steer` (`after`) | Do not interrupt. Queue `text` to the front (`at="head"`) and wait for the current generation to finish. `enqueue` is an alias. |
| `cancel_inflight` | A2A **Cancel Task** (`tasks/cancel`). Drops the remainder of the decode; no follow-up cycle. Success is not guaranteed. |

`inspect_queue` returns the CAS token. Callers retry on `QueueConflict`.
There is no last-write-wins. Turns drain FIFO under the same lock, so a
drop cannot race a pop.

## LLM primitives

These control verbs are not Mealy ticks. They close or continue an
`LLM_CALL` already in `M_model=CALLING`:

| Verb | LLM | `M_model` | Reply |
| --- | --- | --- | --- |
| `steer` (preempt) | Cancel the streamed `ainvoke` between tokens. Keep `append_partial` prefix in working memory. New completion after `OperatorSteerReceived` (operator text in context). | CALLING → IDLE (abort, not DONE) → CALLING | Prefix is not a client `stop`. Continuation is a new assistant message. |
| `steer` (`replace`) | Cancel `ainvoke`, discard partials. New `UserInputReceived` turn. | CALLING → IDLE, `M_dp` IDLE | No prefix in history. Fresh user turn. |
| `steer` (`after`) | Do not touch the in-flight call. | unchanged | Current decode finishes normally (`stop`), then the queued turn runs. |
| `cancel_inflight` | Cancel `ainvoke`, drop remainder. | CALLING → ERROR/IDLE via cancelled return | Error/cancel client response. No follow-up. |

Preempt needs a cancellable decode. `ainvoke` uses `achat_completion_stream` when the provider has it, so cancel lands between chunks even if the spec did not set `stream: true` for UI. Without a stream iterator, cancel still aborts the one-shot await and the prefix is empty.

`finish_reason=preempted` / `replaced` on `EngineIoReturn` means that **decode** ended, not that the agent finished answering. Evaluate does not emit `EmitClientResponse` for those.

## Layers

1. **Kernel operations** — the table above.
2. **Boundary slots** — closed envelope/spec types (`governance`,
   `llm_provider`, `tool_provider`, …). A new slot is a kernel change.
3. **Harness compositions** — named combinations whose leaves are
   operations or slots (`react`, `subagents`, `recovery`, `detective`,
   `whatif`, `plan_mode`, `evolution`). See `mas.runtime.harness`.
4. **Library / product** — skills, related filesystem adapters, execute
   sandboxes, lab steps. These are not envelope slots and are not stored
   in kernel product state `Q`.

Tool execution after ALLOW may run inside an `ExecuteSandbox` (workdir
or a host jail). Coding-agent workspaces are snapshotted as related
state (fingerprint + locator; git or directory-copy adapters). See
[snapshots](snapshots.md).

## Copy-on-write

Python updates kernel state in place. A snapshot copies kernel product
state into a frozen `CowKernel` and freeze-shares working memory. Later
writes do not leak into the frozen node. Restore installs a writable copy.
