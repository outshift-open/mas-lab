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
are merged, history-filtered, and token-trimmed to the model context window
minus completion reserve (overridable via `spec.context_manager.params.trimmer`).
See
[context-segmentation.md](../../context-segmentation.md) and
[context-assembly.md](../../../../docs/manifests/context-assembly.md).

`context_manager` plugins live in `library-standard` (`plugins/context/conversation.py`).
They implement `ContextManagerContract`: return a protocol-valid `messages[]`
prefix from `manage_history` (user-turn atomicity, tool ask then matching
results). The two layers and the rules are on
[ContextManagerContract](#contextmanagercontract). Token trim uses a shared
helper in `library-standard` (`trim_messages_to_budget`), not a registry
plugin type.

---

## ContextManagerContract

Supporting interface for conversation-history trimming and summarization — not a
separate product factor in the Mealy model. **Python:**
`mas.runtime.contracts.context_manager_contract.ContextManagerContract`.
Implementations live in `library-standard` (this page is the interface
contract those plugins must satisfy).

`ContextContract` contributes prompt parts. This contract decides how much of
the **committed conversation** is resent on the next LLM call.

### Two layers of an LLM call

The provider is not “just a bag of tokens,” and it is not reading tool-result
English either. There are two layers:

| Layer | What it is | What it inspects |
|-------|------------|------------------|
| **1. Protocol** | The HTTP body: a typed `messages[]` list (`role`, `tool_calls[].id`, `tool_call_id`, …) | Structure: roles, ids, counts. The body of a tool result (`"12°C"`) is opaque. |
| **2. Tokens** | A chat template flattens those objects into one token stream, then the weights run | Ordinary next-token prediction in the tool-result *slot* of the template |

Layer 1 runs **before** tokenization. A 400 for mismatched tool results is a
failed protocol check, not the model misunderstanding the transcript. LiteLLM
translating to Anthropic/Bedrock is still layer 1: it counts `toolUse` blocks
against following `toolResult` blocks.

The HTTP API is **stateless**. Continuity is only the `messages[]` **we**
resend. If call 1 returned “call tools A and B”, call 2 must include that
assistant message and then the two matching results.

**Call 1 we send**

```text
user: Weather in Paris and London?
```

**Call 1 the model returns** (not stored by the vendor)

```text
assistant: tool_calls = [
  {id: call_1, get_weather, Paris},
  {id: call_2, get_weather, London},
]
```

**Call 2 we send** (previous transcript + ask + both results)

```text
user: Weather in Paris and London?
assistant: tool_calls = [call_1, call_2]
tool: tool_call_id=call_1  "12°C, cloudy"
tool: tool_call_id=call_2  "8°C, rain"
```

### Rules `manage_history` must stick to

`manage_history(past, budget_tokens)` sees **committed** history only. The
current user turn and in-turn working memory are appended *after* this method.
Return value is layer-1 objects, not a token string.

1. **User-turn atomicity.** Slice on `role=user`. Each turn is that user
   message plus everything until the next user (assistant tool asks, `role=tool`
   results, follow-up assistant text). Do not drop a tool ask and keep its
   results, or the reverse.
2. **Ask then results, then anyone else.** After an assistant message with N
   `tool_calls`, the next N messages must be `role=tool` for those ids, same
   count, nothing in between. Then the model may speak again.
3. **Do not compact the live tool round.** That round is working memory, not
   `past`. Summarize or drop only *older* user turns (`keep_turns` stay
   verbatim). If you summarize, cache the summary; do not re-summarize on every
   later call until the managed payload exceeds the budget including
   `hysteresis_ratio`.
4. **Ids over text.** Pair on `tool_calls[].id` / `tool_call_id`. Never parse
   tool-result content to decide what to keep.

The kernel still runs a last-pass pairing repair after assembly
(`sanitize_provider_messages`). Plugins must not rely on that to paper over a
split group; repair fills missing results with empty strings and drops extras.

| Method | Parameters | Notes |
|--------|------------|-------|
| `manage_history(past, budget_tokens)` | committed messages; token hint (model context window minus completion reserve) | Return a possibly shorter `past`. Must remain a valid layer-1 prefix. |

**Runtime path:** `assemble_llm_messages` → `CMFactory` / cached plugin →
`manage_history` → append current user → pin-tail working memory → trim →
sanitize → provider. Manifest: `spec.context_manager` (see
[context-assembly.md](../../../../docs/manifests/context-assembly.md)).

Bundled implementations (not the contract): `StackConversation`,
`SlidingWindowConversation`, `SummarizingConversation` in `library-standard`.

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
