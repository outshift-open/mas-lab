<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Execution tuning (removed from Agent manifests)

**`spec.execution` on `kind: Agent` and overlay `spec.patch.execution` are not supported.**
Engine queue depth, cache policy, streaming, mocking, and parallel tool dispatch
are configured only through **`kind: RuntimeEngine`** manifests resolved like
infra: workspace `runtime_refs`, `$XDG_CONFIG_HOME/mas/runtime/`, env
`MAS_RUNTIME_REFS`, or CLI `--runtime-ref`.

See [runtime-engine.md](runtime-engine.md) and [user-config.md](../user-config.md).

## Migration (removed agent fields)

| Old (invalid on `kind: Agent` / overlay patch) | Replacement |
| --- | --- |
| `spec.execution` (cache, stream, mocking, queue depth, …) | `kind: RuntimeEngine` via `runtime_refs` / `--runtime-ref` / `MAS_RUNTIME_REFS` |
| `spec.execution.mocking` / mock overlay alone | `llm.provider: mock` overlay **plus** workspace `infra_refs: [standard:mock-llm]` (or `--infra-ref`) |
| `spec.infra_refs` / `spec.runtime_refs` on Agent, MAS, or overlay | `config.yaml`, `MAS_INFRA_REFS` / `MAS_RUNTIME_REFS`, `--infra-ref` / `--runtime-ref` |
| `spec.infra_interceptors` on Agent | workspace / CLI infra resolution (same as infra refs) |

**Not the same:** `experiment.execution` in `mas-lab benchmark` YAML is the **batch
orchestration** block (parallel scenarios, timeouts, trace-cache emulation). It does
not replace `RuntimeEngine` and is documented in [experiment.md](experiment.md#execution-batch-orchestration).

`mas-ctl validate` and separation checks fail closed on forbidden keys so outdated
examples surface immediately.
