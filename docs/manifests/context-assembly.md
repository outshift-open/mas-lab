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

`context_manager` plugins slice committed history by **user turn**. After
working memory is appended, assembly runs one pairing pass (one result per
tool call). See [Tool-call pairing](#tool-call-pairing).

---

## `context_manager` plugin (required default)

Resolved via `CMFactory` and `defaults.yaml` (`summarising` when omitted).
Plugins live in **mas-library-standard** (`StackConversation`,
`SlidingWindowConversation`, `SummarizingConversation`). The default strategy
keeps the last `keep_turns` user turns **verbatim** (default **10**, set
`spec.context_manager.params.keep_turns`) — the live tool round is working
memory, not this window — and only then summarizes older history, with
`hysteresis_ratio` (default **0.2**) so a summary is not recomputed on every
later LLM call. Without an LLM summarizer, older turns are dropped instead.

`mas-ctl compile` writes the resolved binding, including recency and trimmer
params derived from the model context window.

Strategy params (`keep_turns`, `max_turns`, `max_messages`, `summary_threshold`, …)
are passed to the plugin constructor. Assembly-only params are stripped before
instantiation (see below).

Instance is **cached per `(ctx, manifest)`** across turns in one session.

---

## Assembly token trim (model context window)

History is capped to **model `context_window` minus completion reserve**
(`models[].max_tokens`). Override with **`spec.context_manager.params.trimmer`**
(not a separate `spec` key and not a registry plugin type):

```yaml
spec:
  models:
    - model: gpt-4o
      max_tokens: 2000          # completion reserve
      context_window: 128000    # input window; compile fills this if omitted
  context_manager:
    type: summarising           # default; sliding-window | stack also valid
    params:
      keep_turns: 10            # recent user turns never summarized (override per agent)
      hysteresis_ratio: 0.2     # don't re-summarize until managed history grows 20% past budget
      working_memory_messages: 20
      trimmer:
        max_tokens: 128000      # defaults to models[].context_window
        reserve_tokens: 2000    # defaults to models[].max_tokens
```

| Field | Meaning |
|-------|---------|
| `trimmer.max_tokens` | Estimated input token ceiling (chars÷4 heuristic + per-message overhead). Defaults to the primary model's `context_window`. |
| `trimmer.token_budget` | Alias for `max_tokens` |
| `trimmer.reserve_tokens` | Subtracted from `max_tokens` before comparing to the payload. Defaults to the primary model's `max_tokens`. |
| `keep_turns` | Last N committed user turns kept verbatim (default 10). Older turns are summarized (or dropped). |
| `hysteresis_ratio` | After a summary, new turns stay verbatim until the managed payload exceeds `budget × (1 + ratio)` (default 0.2). |

In-turn working memory is passed as **`pin_tail`**: oldest tool-call groups in
history are dropped first; WM can be trimmed by group only after history is
exhausted. That is what keeps the live tool round intact for the provider.

The trim implementation lives in **mas-library-standard**
(`trim_messages_to_budget`); the kernel only derives the budget and invokes it.

---

## Working memory count cap

`working_memory_messages` (default **20**) limits how many WM rows are considered
for assembly (tool groups are atomic). This is independent of `trimmer`.

---

## Tool-call pairing

Canonical rules for plugin authors:
[ContextManagerContract](../../runtime/docs/dev/contracts/state-and-context.md#contextmanagercontract)
(two layers: protocol vs tokens; ask-then-results).

The HTTP API is stateless. If the model asked for tools A and B, the next
request we build must contain that assistant message and then those two
results. Assembly runs one pairing pass after `manage_history` and working
memory (one result per tool call). The server checks **ids and counts**, not
the text inside a tool result.

---

## Related

- [agent.md](agent.md) — `working_memory.compaction` facade over `context_manager`
- [ContextManagerContract](../../runtime/docs/dev/contracts/state-and-context.md#contextmanagercontract) — protocol vs tokens, pairing rules for history plugins
- [working-memory-compaction.md](../design/working-memory-compaction.md)
- [plugins-reference.md](../plugins-reference.md) — `StackConversation`, `SlidingWindowConversation`, `SummarizingConversation`

