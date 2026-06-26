<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-ctl User Guide

`mas-ctl` orchestrates multi-agent systems from declarative manifests.

## Who this guide is for

- Teams deploying MAS topologies
- Developers running scenarios against the same MAS definition
- Operators applying environment flavours and policy controls

## Install

```bash
uv pip install -e ctl
```

## Quickstart

Run from a MAS manifest:

```bash
mas-ctl run-mas mas.yaml --flavour local
```

Run with explicit prompt and scenario:

```bash
mas-ctl run-mas mas.yaml --scenario baseline --prompt "Plan a 3-day trip to Paris" --flavour local
```

## Core concepts

- MAS manifest: declares agents, topology/workflow, metadata
- Deployment: placement strategy and runtime binding (`local-inproc` is the only OSS-supported strategy)
- Scenario: named overlay for test or environment-specific variants
- Policy: system-level guardrails and runtime limits

### Placement (OSS)

Only `local-inproc` placement is supported in mas-lab OSS. Strategies
`local-multiprocess`, `docker`, and `kubernetes` are planned for a later release
(2026.3). Compose and plan fail at compose time with a clear error if an
unsupported strategy is used.

## Common tasks

### Validate effective topology

- Inspect resolved contracts and topology before production runs.

### Switch environments

- Keep same MAS manifest; switch only flavour.

### Audit secret usage

- Verify all `*_env` references are present and provided at runtime.

## CLI map

- `chat`, `tui` — interactive conversation
- `run-mas` — execute MAS workflow
- `compose`, `plan` — manifest composition and placement dry-run
- `validate`, `schemas` — YAML validation
- `flavour list`, `flavour show`
- `infra list`, `infra show`
- `registry` — plugin registry introspection
- `checkpoint` — session checkpoints

Benchmarking: **`mas-lab benchmark run`** (see [Tutorial 3](../../docs/tutorials/03-experiments-and-analysis/README.md)).

## Troubleshooting

- Scenario not applied: check scenario name and overlay paths.
- Agent startup failure: validate referenced agent manifests.
- Policy mismatch: inspect effective config output before run.
