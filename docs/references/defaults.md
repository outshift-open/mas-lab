<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Compiled agent defaults

Every field a bare-minimum `Agent` manifest **doesn't** declare is filled in
by `mas-ctl compile` before the runtime ever sees it — the plugin for every
singleton slot (`design_pattern`, `context_manager`, `assembler`), the
sub-plugin composed by one of those (`context_manager.params.summarizer`),
and every attribute each one takes. Omitting a field, writing the plugin
name, and writing the fully-expanded object are the **same runtime
behaviour** ([plugin-bindings.md](../manifests/plugin-bindings.md)) — this
page exists so you don't have to hold that expansion in your head, or worse,
guess at it.

**This page is a worked example, not a schema.** Field-by-field docs (with
the *why*) live on the pages linked from each block below; if a number here
ever looks stale, trust the command over this page and re-run it — see
[Regenerating this page](#regenerating-this-page).

---

## The input: Tutorial 1's minimal manifest

[`docs/tutorials/01-building-an-agent/agent.yaml`](../tutorials/01-building-an-agent/agent.yaml)
declares a model, a description, and a system-prompt fragment. Nothing else:

```yaml
apiVersion: mas/v1
kind: Agent

metadata:
  name: qa-agent

spec:
  models:
    - model: gpt-4o

  description: Answer general knowledge questions.
  context:
    intent: "Answer general knowledge questions."
    role: |
      Answer questions clearly and concisely.
```

## The output: `mas-ctl compile agent.yaml`

```yaml
apiVersion: mas/v1
kind: Agent
metadata:
  name: qa-agent
spec:
  models:
  - model: gpt-4o
    context_window: 128000
  description: Answer general knowledge questions.
  context:
    intent: Answer general knowledge questions.
    role: 'Answer questions clearly and concisely.

      '
  design_pattern:
    type: react@v1
    params:
      max_steps: 512
      max_cot_pass: 1
      parallel: true
  context_manager:
    type: summarising
    params:
      keep_turns: 10
      hysteresis_ratio: 0.2
      summary_threshold: 126000
      summarizer: llm
      working_memory_messages: 20
      trimmer:
        max_tokens: 128000
        reserve_tokens: 2000
  assembler:
    type: assembler
    params:
      emit_segments: true
      always_reassemble: false
```

## What each block is

| Block | Plugin (default) | Attributes | Docs |
|-------|-------------------|------------|------|
| `models[0].context_window` | — | `128000`: the model's input window, filled from the model catalog when omitted | [agent.md](../manifests/agent.md#spec-field-reference) |
| `design_pattern` | `react@v1` (registry alias `react`) | `max_steps` (dispatch-loop cap), `max_cot_pass`, `parallel` | [plugin-bindings.md § design_pattern](../manifests/plugin-bindings.md#design_pattern-default-react) |
| `assembler` | `assembler` (`ContextAssemblerPlugin`) | `emit_segments`, `always_reassemble` — builds `messages[]`; **not** where history policy lives | [plugin-bindings.md § assembler](../manifests/plugin-bindings.md#assembler-default-assembler) · [context-assembly.md](../manifests/context-assembly.md#assembler-required-default) |
| `context_manager` | `summarising` | `keep_turns`, `hysteresis_ratio`, `summary_threshold`, `working_memory_messages`, `trimmer.{max_tokens,reserve_tokens}` | [plugin-bindings.md § context_manager](../manifests/plugin-bindings.md#context_manager-default-summarising) · [context-assembly.md](../manifests/context-assembly.md#context_manager-plugins) |
| `context_manager.params.summarizer` | `llm` (sub-plugin of `summarising`) | none of its own; composed onto the context manager, bound to the agent's live engine at instantiation | [plugin-bindings.md § summarizer](../manifests/plugin-bindings.md#summarizer-sub-plugin-of-summarising) |

Every one of these is a real registered plugin — resolving `type: react@v1`,
`type: summarising`, `type: assembler`, `type: llm` through the same plugin
registry a manifest author's own explicit choice would go through. There is
no hidden "if omitted, do X in code" branch: the default *is* a binding
(`library-standard/library.yaml`'s `defaults:` map), and it is overridable
per-workspace (`config.yaml` `defaults:`) without touching a single agent
manifest. See [config.yaml § defaults](config.yaml.md).

## Regenerating this page

The numbers above will drift as defaults change. Reproduce them yourself
from any manifest — an omitted field and its fully-expanded form are
identical at runtime, so this works on your own agents too, not just the
tutorial:

```bash
cd docs/tutorials/01-building-an-agent
mas-ctl compile agent.yaml --no-header
```

Add `-o overlays/<file>.yaml` (repeatable) to see overlays folded in first —
[compile command reference](../cli/compile.md). To see only what a specific
manifest sets versus package defaults, add `--no-defaults` and diff.

## Related

- [plugin-bindings.md](../manifests/plugin-bindings.md) — the binding shape these defaults fill (string ≡ object, list slots)
- [agent.md](../manifests/agent.md) — every `spec` field, not just the plugin slots shown here
- [context-assembly.md](../manifests/context-assembly.md) — how `assembler` + `context_manager` + `summarizer` cooperate at assemble time
- [working-memory-compaction.md](../design/working-memory-compaction.md) — why `context_manager` is the single history-policy surface
- [Tutorial 1: building an agent](../tutorials/01-building-an-agent/README.md) — the manifest this page compiles
