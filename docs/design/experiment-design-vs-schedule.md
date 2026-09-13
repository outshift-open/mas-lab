<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Experiment manifest: design vs schedule (planned split)

**Status:** design / implementation in progress on `feat/experiment-design-vs-schedule-split`.
**Tracking:** [cisco-eti/ioc-core-mas-lab#54](https://github.com/cisco-eti/ioc-core-mas-lab/issues/54)

**Prerequisite (done):** Agent/MAS/runtime wiring via workspace + `RuntimeEngine`
([PR #69](https://github.com/outshift-open/mas-lab/pull/69)).

## Problem

`experiment.execution` today mixes:

1. **Experimental design** — what conditions we compare (scenarios, overlay axes,
   design mode, dataset, evaluation, replications).
2. **Bench schedule** — how mas-lab walks the matrix (parallelism, timeouts,
   ordering, runner). These do not change the *meaning* of an analysis cell.
3. **Bench emulation** — mock/replay/trace-cache posture, which overlaps workspace
   `infra_refs`, `RuntimeEngine`, and scenario `overlays.infra`.

Only (1) belongs in the experiment *description*. (2) and (3) are execution
machinery.

## Target model (draft keys)

| Concern | Draft YAML home | In analysis design? |
| --- | --- | --- |
| Variation axes | `scenarios[]`, top-level `design`, dataset, evaluation | Yes |
| Deployment wiring | `config.yaml` `infra_refs` / `runtime_refs`, CLI | No (constant unless a factor) |
| Schedule | `schedule.*` | No |
| Bench emulation | `bench_emulation.*` or under `schedule` | Only if emulation is a factor |

## Field migration (from `execution`)

| Current | Target |
| --- | --- |
| `parallel_scenarios`, `timeout`, `pause_between_runs`, `strategy`, `runner` | `schedule.*` |
| `design` | top-level `experiment.design` |
| `emulation.infra` | workspace/CLI or scenario `overlays.infra` when a factor |
| `emulation.runtime.cache` | trace-level bench cache (not RuntimeEngine LLM cache) |
| `execution.infra_refs` | **removed** — use workspace + `--infra-ref` / `--infra` |

## Implementation checklist

- [ ] Schema v2 + dual-read loader with deprecation warnings
- [ ] Codemod `labs/`, tutorials, fixtures, controller templates
- [ ] Update overlay merge and CLI overrides
- [ ] Strict validation: no `execution:` in shipped YAML
- [ ] `task verify` + golden runs

See also [experiment.md](../manifests/experiment.md).
