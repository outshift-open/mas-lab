<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# State and Context Contracts

Session persistence, execution checkpoints, shared coordination, and prompt
context assembly.

See also: [taxonomy.md](taxonomy.md) · [model-and-tools.md](model-and-tools.md) ·
[context-segmentation.md](../../context-segmentation.md)

---

## SessionContract

Durable per-contact conversational state (turn log, windowed history, metadata).

| Method | Purpose |
|--------|---------|
| `load_session(session_id)` | Restore session blob |
| `save_session(session_id, state)` | Persist after turn |
| `list_sessions()` | Enumerate known sessions |

**Runtime path:** `pre_session_access` / `post_session_access` hooks; kernel
`SessionState` tracks in-flight execution. Full intra-turn tool traces are
recorded in `events.jsonl`, not always in session blobs — see
[trajectory-schema.md](../../trajectory-schema.md).

---

## ExecutionSessionContract

Checkpointing of in-flight execution (Mealy-layer state, DP phase, pending egress).

| Method | Purpose |
|--------|---------|
| `checkpoint(execution_id, snapshot)` | Save resumable snapshot |
| `load_execution(execution_id)` | Restore snapshot |
| `latest_execution(session_id)` | Most recent checkpoint for session |

**Runtime path:** `on_pre_checkpoint`, `on_post_checkpoint`, `on_pre_restore`,
`on_post_restore` on the control plane.

---

## SharedContextContract

Multi-agent shared blackboard / coordination store.

| Method | Purpose |
|--------|---------|
| `get(key)` / `set(key, value)` | Read/write shared fields |
| `watch(key, callback)` | Change notifications |
| `acquire_lock(key, timeout)` | Exclusive access |

Used by MAS workflows where agents publish partial results to a shared store.
`ContextContract` contributors may read a snapshot via `collect_context`.

---

## ContextContract

Typed prompt context contribution — the primary extension point for RAG,
memory bridges, skills, and DP instructions.

| Method | Purpose |
|--------|---------|
| `collect_context(request)` | Return `ContextPart` list with provenance |

**Kernel path:** context assembly runs before each scheduled `LLM_CALL`; parts
are merged, history-filtered, and budget-trimmed. See
[context-segmentation.md](../../context-segmentation.md).

Implementations live in `library-standard` (`plugins/context/*`) and custom
lab plugins.

---

## ContextManagerContract

Supporting interface for conversation-history trimming and summarization — not a
separate product factor in the Mealy model.

| Method | Purpose |
|--------|---------|
| `manage_history(messages, budget)` | Return trimmed or summarized history |

Invoked during the filter-history sub-phase of \(M_{\text{ctx}}\). Examples:
`StackConversation`, `SummarizingConversation` in `library-standard`.

---

## Implementation status

| Contract | Kernel integration | Typical plugin location |
|----------|-------------------|-------------------------|
| `context` | Hot path (every LLM egress) | `library-standard` |
| `context_manager` | Hot path | `library-standard` |
| `session` | Turn boundaries | flavour-dependent |
| `execution` | Checkpoint commands | ctl checkpoint CLI |
| `shared_context` | MAS workflows | lab / sample apps |

Contract classes are declared in `mas.runtime.contracts.base`; concrete plugins
register via `plugin_id` and manifest `spec.plugins`.
