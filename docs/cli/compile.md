<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# `mas-ctl compile`

Apply a manifest plus overlay stack and write the **resolved spec**: overlays
merged, omitted runtime defaults filled. That is the in-memory Agent or MAS
dict `chat` / `run-mas` hold **before** bootstrap wiring (delegation tools,
skill injection, expanding tool refs to files).

`mas-ctl compose` is different: it emits **EffectiveBind** + **placement**.
Use `compile` to inspect or snapshot YAML; use `compose` to inspect runtime
bind and placement.

Terms: [glossary.md](../glossary.md) · overlays: [overlay.md](../manifests/overlay.md)

## Basic usage

```bash
# Tutorial 1 — stdout (one Agent document)
mas-ctl compile docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/skills.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/memory.yaml

# One agent → one file
mas-ctl compile agent.yaml -o overlays/tools.yaml -O compiled-agent.yaml

# MAS → folder (mas.yaml + agents/, refs rewritten)
mas-ctl compile mas.yaml -o overlays/linear.yaml -O ./compiled/

# MAS → one file with agents inlined under spec.agency.agents
mas-ctl compile mas.yaml -o overlays/linear.yaml --layout bundle -O team.yaml
```

`--output` / `-O` is a **folder** for a MAS tree, or a **file** for a single
agent (and for `--layout bundle`). Omit it to print a bundle document on stdout.

## Layout: tree vs bundle vs auto

| Layout | Agent | MAS | When to use |
|--------|-------|-----|-------------|
| **auto** (default) | file / stdout | directory → tree; `.yaml` → bundle | Usual CLI |
| **tree** | `agent.yaml` in a folder | `mas.yaml` + original `agents/…` paths | Diff, re-validate, re-run with the same file layout |
| **bundle** | one Agent YAML | one MAS YAML with **inlined** Agent documents | Snapshot, review, “what did the runtime see?” |

Inlining a whole MAS in one file is **valid** (`agency.agents` may be either
`{id, ref}` or a full `kind: Agent` document). It is the best match for the
in-memory tree. A folder of files is better for editing and for
`mas-ctl validate` / `run-mas` that still expect separate agent files.

Relative tool/skill refs are **not** rewritten. Library scheme refs
(`samples:tools/…`) stay portable; `../../tools/foo.tool.yaml` still resolves
from the original agent directory, not from the compiled tree.

## Defaults

Omitted fields are filled from the same accessors the runtime uses
(`defaults.yaml` / workspace `defaults.model`):

- `spec.design_pattern` (package default `react`; string `design_pattern: cot` ≡ `{type: cot}`. Compile fills `params.max_steps: 512`, `max_cot_pass: 1`, `parallel: true`)
- `spec.models[0]` (workspace or package default model, plus `context_window`)
- `spec.context_manager` (`summarising`, `keep_turns` 10, `hysteresis_ratio` 0.2, `summarizer: llm`, trimmer from the model window)
- `spec.assembler` (package default `assembler`; compile fills `emit_segments: true`, `always_reassemble: false`)

Pass `--no-defaults` to emit overlay merge only. Explicit values are never
overwritten.

## Flags

| Flag | Description |
|------|-------------|
| `-o / --overlay` | Overlay YAML (repeatable, later wins) |
| `-O / --output` | Directory or YAML file |
| `--layout auto\|tree\|bundle` | Output shape (see table) |
| `--no-defaults` | Skip filling runtime defaults |
| `--no-validate` | Skip schema validation |
| `--no-header` | Omit the generated-by comment |

Flavour and infra overlays are skipped (compile emits Agent/MAS specs only).
MAS overlays cannot be applied to an Agent manifest.

## See also

- [Tutorial 1](../tutorials/01-building-an-agent/README.md) — overlay stack
- [Tutorial 2](../tutorials/02-creating-a-mas/README.md) — MAS topology overlays
- [`mas-ctl compose`](mas-ctl.md#other-commands) — EffectiveBind + placement
