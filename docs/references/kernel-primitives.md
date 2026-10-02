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

Plugin code, an LLM tool advertisement, and an admin caller (`ControlContract`,
including the unix-socket adapter) call the same functions.

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
