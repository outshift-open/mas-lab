<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Plugin id cards (MAS Library Standard)

Each plugin has a canonical **`plugin_id@version`**. Short names resolve via [`library-samples/aliases/plugin-aliases.yaml`](../../library-samples/aliases/plugin-aliases.yaml).

## Template

| Field | Example |
|-------|---------|
| **ID** | `react@v1` |
| **Alias** | `react` |
| **Kind** | design_pattern \| memory \| workflow \| tool \| governance \| observability |
| **Implementation** | Native Mealy plugin in `mas.runtime` |
| **TLA** | `ReactPattern.tla` |
| **Wraps** | None (not LangChain) |
| **Manifest keys** | `spec.design_pattern.type`, `--pattern` |
| **Used by** | Tutorial 01 default, design-space lab |

---

## Design patterns (`mas.runtime.machines.design_pattern`)

| ID | Alias | TLA | Implementation |
|----|-------|-----|----------------|
| `react@v1` | react | ReactPattern.tla | Native — reference Mealy δ |
| `cot@v1` | cot | CoTPattern.tla | Extends react, extra LLM pass |
| `introspection@v1` | reflection | CoTPattern.tla | min 2 passes (critique) |
| `plan_execute@v1` | plan_execute | DesignPatternScheduler.tla | JSON plan → kernel tool schedule |
| `tree_of_thoughts@v1` | tot | DesignPatternScheduler.tla | Multi-pass thought scoring |
| `single_pass@v1` | linear | — | One LLM call, no tool loop |

## Memory

| ID | Alias | TLA | Implementation |
|----|-------|-----|----------------|
| `memory-semantic@v1` | memory | MemoryMachine.tla | SQLite FTS5 (`boundary/memory/semantic.py`) |
| memory seeds | — | — | YAML overlay + `MemorySeedLoader` |

## Workflow (`mas.ctl.orchestration`)

| ID | Alias | Release | Notes |
|----|-------|---------|-------|
| `workflow-sequential@v1` | workflow-sequential | 2026.1 | Topological DAG |
| `workflow-graph@v1` | workflow-graph | 2026.1 | Graph topology |
| `workflow-supervised@v1` | workflow-supervised | 2026.1 | Operator approve between nodes |

## Tools (native registry)

| Name | Source | Notes |
|------|--------|-------|
| calculator | `tools/registry.py` | Native |
| web-search | `tools/registry.py` | ddgs + file cache |
| verify_fact | `tools/registry.py` | Tutorial apple scenario |
| memory-search | `tools/registry.py` | Uses semantic FTS store |

## Deferred (not in this OSS release)

Docker/K8s placement, Petri-net workflow, Letta memory, and extended OTel plugins are planned for a later release.
