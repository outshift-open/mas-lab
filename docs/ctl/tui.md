<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# `mas-ctl` terminal UI (TUI)

`mas-ctl tui` is a curses chat UI with the same bootstrap as `mas-ctl chat`:
**manifest** merge, **overlays**, infra refs, HITL, and **observability**.

Terms: [glossary.md](../glossary.md).

Use the TUI for long interactive sessions. Use `mas-ctl chat` for scripts and
`--trace` (exchange log). Use the [web UI](../ui/index.md) to browse **benchmark**
history. Use `mas-lab benchmark run` for **experiments** with an **embedded pipeline**.

You need an **agent** or **MAS** manifest first
([Tutorial 1](../tutorials/01-building-an-agent/README.md)).

## Basic usage

```bash
mas-ctl tui agent.yaml
mas-ctl tui mas.yaml -o overlays/governance/hitl-on-tool.yaml
mas-ctl tui agent.yaml -o docs/schemas/examples/overlays/observability-native.yaml
```

## Flags (parity with `mas-ctl chat`)

| Flag | Description |
|------|-------------|
| `-o / --overlay` | **Overlay** YAML (repeatable) |
| `--pattern` | Design-pattern plugin alias |
| `--infra-ref` | Infra bundle (`standard:openai`, …) |
| `--memory-seed` | Seed file for memory plugins |
| `--single-turn` | Exit after one user turn |
| `--no-validate` | Skip manifest validation |

### Observability

| Flag | Description |
|------|-------------|
| `--events` / `--no-events` | Override manifest **observability** |
| `--events-file PATH` | **`events.jsonl`** output path |
| `--events-stdout` | Stream JSONL on stderr |
| `--events-format` | `native` · `boundary` · `both` · `otel` |

Full reference: [cli/observability.md](../cli/observability.md).

`--trace` (exchange log) is on **`chat` only**:

```bash
mas-ctl chat agent.yaml -i --trace --events --events-file traces/events.jsonl
mas-ctl tui agent.yaml --events --events-file traces/events.jsonl
```

## HITL

Governance **overlays** that require human approval work in the TUI like in chat.

## When to use what

| Tool | Best for |
|------|----------|
| `mas-ctl chat` | Scripts, **exchange log**, CI smoke |
| `mas-ctl tui` | Interactive terminal, HITL |
| Web UI | **Run** history, plots, demos |
| `mas-lab benchmark run` | **Scenarios**, **dataset**, **embedded pipeline** |

## Related

- [user-guide.md](../user-guide.md)
- [cli/observability.md](../cli/observability.md)
- [Tutorial 1](../tutorials/01-building-an-agent/README.md)
