<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Plugin bindings in manifests

How an agent spec **names a plugin** and **passes its parameters**. Applies to
every cardinality-one slot (`design_pattern`, `context_manager`, `assembler`,
`memory` shorthand) and to list slots (`governance`, `observability`,
`context_sources`).

**Schema:** `docs/schemas/runtime/agent.schema.yaml` · **Code:**
`mas.runtime.spec.plugin_binding.normalize_plugin_binding`

Omitting a slot, writing the plugin name, and writing the full object with
schema defaults are the **same runtime behaviour**. `mas-ctl compile` prints
the full object so you can diff it — see
[Compiled agent defaults](../references/defaults.md) for a worked example
(Tutorial 1's minimal manifest, compiled).

---

## Two shapes

### 1. Singleton slot (one plugin)

The spec **key is the role** (`design_pattern`, `context_manager`, `assembler`).
The **value is the plugin name**, optionally with parameters.

String shorthand and object form are equivalent:

```yaml
# shorthand — plugin name only
spec:
  design_pattern: cot          # ≡ {type: cot}  (allowed)
  context_manager: summarising
  assembler: assembler
  memory: semantic
```

There is no `_plugin` suffix on spec keys. Registry type names match the slot
(`design_pattern`, `context_manager`, `assembler`). Sub-plugins (today:
`context_manager.params.summarizer`) use the same shorthand:
`summarizer: llm` ≡ `{type: llm}`.

`params` (alias `config` on `design_pattern` only) are constructor/kernel
kwargs. `ref` is the long locator (`mas.cm.stack`, `module://…`) when you are
not using a short name.

### 2. List slot (several plugins)

The spec key is still the role. Each list item is **the plugin name**, either
bare or as a one-key map of parameters:

```yaml
spec:
  governance:
    - sample_governance:
        hitl_on_tool: true
        hitl_mode: interactive
    - no_undeclared_tool
  observability:
    - native
```

Default for every list slot is **empty** (no plugins). Native observability is
attached by the flavour / CLI, not by omitting `spec.observability`.

---

## Package defaults and equivalent explicit config

Omitted fields are filled from `defaults.yaml` (overridable in workspace
`config.yaml` `defaults:`). Compile writes the object form below.

### `design_pattern` (default `react`)

Omit the field, write `design_pattern: react`, or:

```yaml
spec:
  design_pattern:
    type: react                # aliases: react@v1
    params:
      max_steps: 512           # kernel dispatch cap (KernelConfig.max_auto_steps)
      max_cot_pass: 1          # extra CoT refinement passes
      parallel: true           # parallel tool calls
```

`design_pattern: cot` is the same shape with `type: cot` (same default
params). Other shipped ids: `single_pass`, `introspection`, `plan_execute`,
`tree_of_thoughts`, `deterministic_single`, `deterministic_linear`,
`deterministic_parallel`.

| Param | Maps to | Default | Who uses it |
|-------|---------|---------|-------------|
| `max_steps` | `KernelConfig.max_auto_steps` | 512 | every pattern (loop cap) |
| `max_cot_pass` | `KernelConfig.max_cot_pass` | 1 | `cot`, `introspection`, `tree_of_thoughts` (min 2 internally) |
| `parallel` | `KernelConfig.parallel_tool_calls` | true | `react` and tool-calling patterns |

### `assembler` (default `assembler`)

```yaml
spec:
  assembler:
    type: assembler            # aliases: context-assembler, ctx-assembler
    params:
      emit_segments: true
      always_reassemble: false
      # token_budget: omit = no part-eviction budget
```

One shipped assembler (`ContextAssemblerPlugin`). History policy is
**not** assembler params; it is `spec.context_manager`.

### `context_manager` (default `summarising`)

Each manager **is** a plugin with strategy code (not an empty shell).

```yaml
spec:
  context_manager:
    type: summarising
    params:
      keep_turns: 10
      hysteresis_ratio: 0.2
      summarizer: llm          # sub-plugin; ≡ {type: llm}. Alternative: drop
      summary_threshold: 126000  # compile: context_window − max_tokens
      working_memory_messages: 20
      trimmer:
        max_tokens: 128000     # models[].context_window
        reserve_tokens: 2000   # models[].max_tokens
```

`sliding-window` equivalent: `{type: sliding-window, params: {keep_turns: 10}}`
(older turns dropped, no summarizer). `stack` equivalent: `{type: stack}`
(optional `max_messages`). Full examples: [context-assembly.md](context-assembly.md).

### `summarizer` (sub-plugin of `summarising`)

Not a top-level spec key. Registry type `summarizer`, composed by the
summarising context manager:

| Plugin | Default? | Behaviour |
|--------|----------|-----------|
| `llm` | yes | this agent's engine (`summarize_messages`); degrades to drop without a live engine |
| `drop` | | discard older turns; keep `keep_turns` verbatim |

```yaml
# default (inside summarising)
params:
  summarizer: llm              # ≡ {type: llm}

# explicit drop
params:
  summarizer: drop             # ≡ {type: drop}
```

### `memory`

Shorthand `memory: semantic` ≡ plugin `semantic`. Full object form is
`memory.types[]` (see [agent.md](agent.md)). Absent → flavour decides.

### List plugins

| Slot | Default | Shipped plugins |
|------|---------|-----------------|
| `governance` | `[]` | `sample` / `sample_governance`, `no_undeclared_tool` |
| `observability` | `[]` (flavour/CLI may attach `native`) | `native`, `otel` |
| `context_sources` | `[]` | `native`, `adk`, `langchain` (skill engines) |
| `providers` | `[]` (implicit local owns `spec.tools`) | `local` |

---

## Compaction

`spec.working_memory.compaction` is **sugar** for `spec.context_manager`.
The context manager owns recency: `manage_history` bounds the LLM view, and
after each turn commit the same cap is written back to `committed_messages`
and conversation chunks (folded prefix data is dropped). Hysteresis on the
context-manager instance avoids a summarizer LLM call on every in-turn step.
Prefer `spec.context_manager`. If both are set, `context_manager` wins.

`stack` with no `max_messages` has no recency cap. Set `max_messages`, or
use the default `summarising` / `sliding-window` plugins.

---

## Overlay merge

Singleton plugin slots (`design_pattern`, `context_manager`, `assembler`)
use `plugin_binding_merge`:

- A string overlay (`context_manager: stack`) replaces the binding.
- Same `type`/`ref` (or a params-only patch) **deep-merges** `params` (nested
  maps keep sibling keys: patching `trimmer.reserve_tokens` does not drop
  `trimmer.max_tokens`).
- A `type`/`ref` change replaces the binding — leftover constructor kwargs
  from the previous plugin are dropped.

On `design_pattern`, `params` wins over the legacy `config` alias when both
are present.

```yaml
# base
spec:
  context_manager:
    type: summarising
    params: {keep_turns: 10}

# overlay — type change drops keep_turns
spec:
  context_manager:
    type: stack
# result: {type: stack}

# overlay — same type keeps and patches params
spec:
  context_manager:
    params: {hysteresis_ratio: 0.3}
# result: {type: summarising, params: {keep_turns: 10, hysteresis_ratio: 0.3}}

# overlay — nested params keep siblings
spec:
  context_manager:
    params:
      trimmer: {reserve_tokens: 4000}
# result trimmer: {max_tokens: 128000, reserve_tokens: 4000}  (if base had both)
```

A slot that is not a plugin name or `{type, ref, params}` object is a hard
error (`PluginBindingError`) **at `mas-ctl compile`/`validate`**, including
when compile runs with `--no-validate` — authoring is the validation
boundary, so this always fails loudly there.

The kernel's own runtime read of an already-compiled manifest is lenient by
design (`normalize_plugin_binding_lenient`): a malformed value that reached
the runtime anyway (a manifest built by hand in a test or a direct
embedding, bypassing `mas-ctl`) is treated as omission — the slot's platform
default is used — rather than failing every turn. Author your manifests
through `mas-ctl compile`/`validate` and you'll never see this distinction;
it only matters if you construct a manifest dict yourself.

---

## Related

- [Compiled agent defaults](../references/defaults.md) — Tutorial 1's minimal manifest, fully expanded
- [agent.md](agent.md) — every agent spec field
- [context-assembly.md](context-assembly.md) — assembler, context managers, summarizers
- [runtime/docs/agent-defaults.md](../../runtime/docs/agent-defaults.md)
- [plugins-reference.md](../plugins-reference.md) — catalog of registered plugins
