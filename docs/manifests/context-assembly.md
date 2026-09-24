<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Context assembly

**Code:** `ContextAssemblerPlugin.assemble_messages` · kernel dispatcher
`mas.runtime.boundary.context.assemble` · **Schema:** `agent.schema.yaml`
(`spec.assembler`, `spec.context_manager`) · **Bindings:** [plugin-bindings.md](plugin-bindings.md)

Each LLM call builds `messages[]` in a fixed order (`spec.assembler`, default
`assembler`):

1. System band (injected context, memory seeds, `collect_context` parts)
2. **Committed history** — after `ContextManagerContract.manage_history`
3. Current user turn (`last_user_text`)
4. **In-turn working memory** (assistant/tool rows from the dispatch loop)

`context_manager` plugins slice committed history by **user turn**. After
working memory is appended, assembly runs one pairing pass (one result per
tool call). See [Tool-call pairing](#tool-call-pairing).

Compaction is not a mutation of in-turn working memory. `manage_history`
bounds the LLM view; after each turn commit the same cap is written back to
the stored log. The summarising plugin caches the last summary
(**hysteresis**) so the summarizer LLM is not called on every in-turn step.

---

## `assembler` (required default)

Builds `messages[]`. Omit the field, write `assembler: assembler`, or write
the object — same behaviour.

```yaml
# default (all three equivalent)
#   (omit)
#   assembler: assembler
spec:
  assembler:
    type: assembler            # alias: context-assembler → mas.ctx.assembler
    params:
      emit_segments: true      # default
      always_reassemble: false # default
      # token_budget: omit = no part-eviction budget
```

There is one shipped assembler (`ContextAssemblerPlugin`). History policy is
**not** assembler params; it is `spec.context_manager`.

---

## `context_manager` plugins

Each manager **is** a plugin with strategy code (not an empty shell). The
summarising manager additionally composes a **summarizer sub-plugin**
(registry type `summarizer`: `llm` | `drop`).

Instance is cached per `(ctx, manifest)` so hysteresis can reuse a summary.

### `summarising` (package default)

Omit `context_manager`, write `context_manager: summarising`, or:

```yaml
spec:
  context_manager:
    type: summarising
    params:
      keep_turns: 10
      hysteresis_ratio: 0.2
      summarizer: llm            # agent's model; drop = discard older turns
      summary_threshold: 126000  # compile: context_window − max_tokens
      working_memory_messages: 20
      trimmer:
        max_tokens: 128000
        reserve_tokens: 2000
```

The plugin keeps the last `keep_turns` user turns verbatim, then asks the
summarizer to compress older turns. `summarizer: llm` uses this agent's
model; without a live engine it behaves like `drop`. Hysteresis (0.2) is the
cache: a new summary is not computed until the managed payload exceeds
budget × 1.2.

### `sliding-window`

```yaml
spec:
  context_manager: sliding-window   # ≡ {type: sliding-window, params: {keep_turns: 10}}
```

Explicit:

```yaml
spec:
  context_manager:
    type: sliding-window        # alias: sliding_window
    params:
      keep_turns: 10            # aliases: window_size, max_turns
```

Older turns are **dropped** (no summarizer).

### Summarizer sub-plugins

Not a top-level spec key. Bound only on `type: summarising`:

| Plugin | Omit / shorthand | Equivalent | Behaviour |
|--------|------------------|------------|-----------|
| `llm` (default) | `summarizer: llm` | `{type: llm}` | Agent's live engine; degrades to drop without one |
| `drop` | `summarizer: drop` | `{type: drop}` | Discard older turns |

The context manager owns recency (`keep_turns`) and the hysteresis cache.
The summarizer only returns summary text (or nothing, which means drop).
The live engine is bound when the context manager is instantiated from
`ctx.engine`, not stored in the spec.

### `stack` (alias `full-history`)

```yaml
spec:
  context_manager: stack
```

```yaml
spec:
  context_manager:
    type: stack                 # or full-history
    params:
      max_messages: 200         # omit = no recency cap; pairing still repaired
```

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
(`trim_messages_to_budget`). Pairing repair, history slicing, working-memory
caps, and compile defaults live under `lib/context/`. The assembler plugin
uses those helpers; `mas-ctl compile` uses the same defaults. The kernel does
not. The kernel raises `ProviderPayloadError` if pairing is still broken after
the plugin returns (survives `python -O`). Custom `spec.assembler` plugins must
produce a paired payload; they can call `sanitize_provider_messages`.

After each turn commit the kernel asks the assembler plugin to apply the same
recency policy to `committed_messages` and conversation chunks. Folded prefix
data is dropped, so snapshots stay bounded (`keep_turns` / `max_turns` /
`max_messages`). Hysteresis still avoids re-summarizing every in-turn LLM call.

A `context_manager` value that is neither a plugin name nor a `{type, ref,
params}` object is a hard error at `mas-ctl compile`/`validate` time. At
assemble time the kernel is lenient instead: a malformed value that reached
the runtime anyway (bypassing `mas-ctl`) is treated as omission and the
default context manager is used, so one bad field cannot fail every turn.
See [plugin-bindings.md](plugin-bindings.md#two-shapes).

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
memory (one result per tool call). The kernel then raises
`ProviderPayloadError` if the payload is still unpaired. The server checks
**ids and counts**, not the text inside a tool result.

---

## Related

- [Compiled agent defaults](../references/defaults.md) — `assembler` + `context_manager` + `summarizer`, fully expanded
- [plugin-bindings.md](plugin-bindings.md) — string shorthand vs `{type, params}` vs list slots
- [agent.md](agent.md) — `working_memory` (live round + persistent buffer; compaction is sugar)
- [ContextManagerContract](../../runtime/docs/dev/contracts/state-and-context.md#contextmanagercontract)
- [working-memory-compaction.md](../design/working-memory-compaction.md)
- [plugins-reference.md](../plugins-reference.md)

