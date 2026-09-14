<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Context assembly (kernel path)

**Code:** `mas.runtime.boundary.context.assemble` · **Schema:** `context-manager-assembly-params.schema.yaml`

Each LLM call builds `messages[]` in a fixed order:

1. System band (injected context, memory seeds, `collect_context` parts)
2. **Committed history** — after `ContextManagerContract.manage_history`
3. Current user turn (`last_user_text`)
4. **In-turn working memory** (assistant/tool rows from the dispatch loop)

`context_manager` plugins must return **provider-safe** committed history (valid
tool-call / tool-result pairing). Tests use `assert_provider_payload`; the kernel
does not run a separate “repair” pass.

---

## `context_manager` plugin (required default)

Resolved via `CMFactory` and `defaults.yaml` (`sliding-window` when omitted).
Strategy params (`max_turns`, `max_messages`, `summary_threshold`, …) are passed
to the plugin constructor. Assembly-only params are stripped before instantiation
(see below).

Instance is **cached per `(ctx, manifest)`** across turns in one session.

---

## Optional assembly token trim

Enable only by setting **`spec.context_manager.params.trimmer`** (not a separate
`spec` key and not a registry plugin type):

```yaml
spec:
  context_manager:
    type: sliding_window
    params:
      window_size: 20
      working_memory_messages: 20
      trimmer:
        max_tokens: 12000
        reserve_tokens: 512   # optional, default 512
```

| Field | Meaning |
|-------|---------|
| `trimmer` | When present with `max_tokens`, run tool-group-aware trim on the assembled list before the provider call |
| `trimmer.max_tokens` | Estimated input token ceiling (chars÷4 heuristic + per-message overhead) |
| `trimmer.token_budget` | Alias for `max_tokens` |
| `trimmer.reserve_tokens` | Subtracted from `max_tokens` before comparing to the payload |

When trim runs, in-turn working memory is passed as **`pin_tail`**: oldest
tool-call groups in history are dropped first; WM can be trimmed by group only
after history is exhausted. When **`trimmer` is omitted**, WM messages are
appended with no token-based trim.

The trim implementation lives in **mas-library-standard**
(`trim_messages_to_budget`); the kernel only reads params and invokes it when
trimmer is configured.

---

## Working memory count cap

`working_memory_messages` (default **20**) limits how many WM rows are considered
for assembly (tool groups are atomic). This is independent of `trimmer`.

---

## Related

- [agent.md](agent.md) — `working_memory.compaction` facade over `context_manager`
- [working-memory-compaction.md](../design/working-memory-compaction.md)
- [plugins-reference.md](../plugins-reference.md) — `StackConversation`, `SlidingWindowConversation`, `SummarizingConversation`
