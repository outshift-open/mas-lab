<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# `config.yaml` reference

Workspace (and user) YAML for **`mas-ctl`** / **`mas-lab`** defaults. Schema:
[`docs/schemas/config.schema.yaml`](../schemas/config.schema.yaml)
(`additionalProperties: false` on the workspace file).

**Secrets never belong in this file.** Put API keys in the dotenv named by
`mas_ctl.env` (default `.env`) or the process environment. Infra manifests
reference the env **name** (`api_key_env`), not the value.

Paths / XDG layout: [user-config.md](../user-config.md).
CLI flags that override these keys: [mas-ctl.md](../cli/mas-ctl.md).

---

## Which file is loaded

| File | Role |
|------|------|
| `<project>/config.yaml` | Workspace — walk up from cwd, or `MAS_WORKSPACE_ROOT` |
| `$XDG_CONFIG_HOME/mas/config.yaml` | User fallback (`mas-lab init` writes this) |

Canonical samples:

- [`library-samples/sample-workspace/config.yaml`](../../library-samples/sample-workspace/config.yaml)
- Tutorials 0–3 under `docs/tutorials/*/config.yaml` (and Tutorial 0 `config.*.example.yaml`)
- Init template: [`lab/src/mas/lab/templates/init/config.yaml`](../../lab/src/mas/lab/templates/init/config.yaml)

### `mas_ctl` merge (exchange log and friends)

For `mas_ctl.trace*` (and the rest of the `mas_ctl` map used by chat / run-mas):

1. CLI flags
2. Workspace `config.yaml`
3. User `$XDG_CONFIG_HOME/mas/config.yaml`
4. Built-ins (`trace` off unless set; when on, summary + timestamps, color off)

---

## Top-level keys (workspace schema)

| Key | Type | Purpose |
|-----|------|---------|
| `mas_ctl` | object | Defaults for `mas-ctl chat` / `run-mas` / validate |
| `mas_lab` | object | Defaults for `mas-lab` benchmark / demo |
| `infra_refs` | string or list | Infra bundles (left-to-right). Override: `MAS_INFRA_REFS`, CLI `--infra-ref` |
| `runtime_refs` | string or list | `RuntimeEngine` refs. Omit for package defaults. Override: `MAS_RUNTIME_REFS`, `--runtime-ref` |
| `infra_interceptors` | string or list | Optional interceptor bundle refs |
| `manifest_libraries` | map name → path | Extra libraries relative to the workspace root |
| `aliases` | map | Runtime plugin alias → canonical URN |
| `defaults` | object | Overrides for runtime `defaults.yaml` (`model`, `design_pattern`, `context_manager`, `assembler`) |
| `paths` | object | `labs_dir`, `cache_dir`, `runs_dir` (else XDG / `MAS_*`) |

---

## `mas_ctl`

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `flavour` | string | `local` | Flavour name (`library-standard` / workspace `flavours/`) |
| `env` | string | `.env` | Gitignored secrets **filename** relative to the workspace |
| `deployment` | string | — | Deployment manifest path (relative to workspace) |
| `runtime_id` | string | — | Kernel / runtime id override |
| `runtime_profile` | string | — | Path to a runtime-profile manifest |
| `trace` | `off` · `summary` · `full` or bool | `off` | Human exchange log on **stderr**. `true` = `summary`. `full` is the payload dump. Color is **not** implied |
| `trace_timestamps` | bool | `true` when tracing | UTC + elapsed on each exchange |
| `trace_color` | bool | `false` | ANSI color (opt-in; same as `--trace-color`) |
| `trace_engine` | bool | `false` | Raw engine I/O JSON (same as `--trace-engine` / `-vv`) |

```yaml
mas_ctl:
  flavour: local
  env: .env
  trace: summary          # off | summary | full
  # trace_timestamps: true
  # trace_color: false    # never implied by trace: summary
  # trace_engine: false
```

`--trace` on the CLI is the one-shot form of `trace: summary`.
`--trace full` is `trace: full`. `--no-trace` disables a config default.

Machines use `events.jsonl` / `mas-lab telemetry`, not this log.
See [mas-ctl.md](../cli/mas-ctl.md#exchange-log) and
[observability.md](../cli/observability.md).

---

## `mas_lab`

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `flavour` | string | `local` | Lab / demo flavour |
| `benchmark_flavour` | string | — | Flavour for `mas-lab benchmark run` |
| `benchmark.clean_stale_outputs` | bool | `false` | Drop output folders for scenarios no longer in `experiment.yaml` |
| `benchmark.clean_stale_trace_cache` | bool | `true` | When cleaning stale outputs, drop unused trace-cache entries |
| `labs_search_paths` | string or list | — | Extra dirs to scan for `*.lab` / experiment YAML (not `paths.labs_dir`) |

---

## `defaults`

| Key | Purpose |
|-----|---------|
| `model` | Default model id when a manifest omits one |
| `design_pattern` | Default plugin id for `spec.design_pattern` |
| `context_manager` | Default plugin id for `spec.context_manager` |
| `assembler` | Default plugin id for `spec.assembler` |

See [runtime/docs/agent-defaults.md](../../runtime/docs/agent-defaults.md).

---

## `paths`

| Key | Purpose |
|-----|---------|
| `labs_dir` | Benchmark run output root |
| `cache_dir` | Cache root (trace cache defaults to `<cache_dir>/traces` when set) |
| `runs_dir` | Agent session run folders |

Env overrides: [user-config.md](../user-config.md). Relative paths resolve from
**the directory of the config file that declared them**.

---

## User-file extras (`mas-lab init` / Tutorial 0)

`$XDG_CONFIG_HOME/mas/config.yaml` is a hybrid: it may include workspace keys
above **and** these fields used by user-config loading (not all are in the
workspace schema):

| Key | Purpose |
|-----|---------|
| `default_infra` | Infra used when no `--infra-ref` / workspace `infra_refs` |
| `default_runtime` | Default `RuntimeEngine` when no `--runtime-ref` / `runtime_refs` |
| `cache_dir` | Top-level alias for `paths.cache_dir` |
| `runs_dir` / `labs_dir` | Top-level path aliases in the Tutorial 0 user example |

Example: [`docs/tutorials/00-environment-setup/config.example.yaml`](../tutorials/00-environment-setup/config.example.yaml).

---

## Example (workspace)

```yaml
mas_ctl:
  flavour: local
  env: .env
  trace: summary

mas_lab:
  flavour: local
  benchmark_flavour: local-benchmark

# infra_refs:
#   - standard:openai
```

Offline CI pairs `standard:openai` with `tests/fixtures/llm-cache/ci-replay.yaml`
via `--infra-ref` / `MAS_INFRA_REFS` — still no secrets in YAML.
