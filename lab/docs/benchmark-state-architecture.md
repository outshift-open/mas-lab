<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Benchmark run state and locking

How `mas-lab benchmark run` tracks progress, avoids duplicate work, and stays safe
under concurrent invocations.

**Prerequisite:** [benchmark.md](benchmark.md) (execution vs pipeline phases).

## Phases

```text
validate YAML → schedule (scenario × item × run) → execute runs → post pipeline
```

| Phase | Skip when |
|-------|-----------|
| Run execution | Trace fingerprint matches cache (`run_info.json` + content hash) |
| Pipeline step | Step fingerprint unchanged (`.cache/<step>.fingerprint`) |

Re-run the same command to resume or refresh outputs:

```bash
mas-lab benchmark run experiment.yaml --progress
```

Force re-execution: `--force` (runs) or `benchmark pipeline run ... --force STEP`.

## Trace cache

Completed runs store traces under the configured cache root (default
`$XDG_CACHE_HOME/mas/traces/` when `$XDG_CONFIG_HOME/mas/config.yaml` is present). Run directories
may contain `.run_ref` symlinks into the cache instead of duplicating JSONL.

Configure: [docs/user-config.md](../../docs/user-config.md).

## Advisory lock

Each experiment output directory uses a PID-based lock (`.benchmark.lock`) so two
`benchmark run` processes do not corrupt the same tree. Stale locks (dead PID) can
be broken with `--force`.

Implementation: [`lab/components/bench/src/mas/lab/benchmark/lock.py`](../components/bench/src/mas/lab/benchmark/lock.py).

## Inspect state

```bash
mas-lab benchmark show last
mas-lab benchmark show last tree
mas-lab benchmark list --limit 10
```

## Related

- [docs/reproducibility.md](../../docs/reproducibility.md) — metadata and sharing
- [PIPELINE_DESIGN.md](../components/bench/PIPELINE_DESIGN.md) — step fingerprints
