<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# User-Level Configuration

Canonical path variables and their defaults live on this page. In other docs,
prefer **`$XDG_*` / `MAS_*` names** (not hardcoded home paths). MkDocs tutorials
can include values via
[`includes/mas-paths.md`](includes/mas-paths.md) snippets (`task docs-gen`).

Field-by-field `config.yaml` keys (including `mas_ctl.trace`) are in the
[config.yaml reference](references/config.yaml.md). CLI flags:
[mas-ctl.md](cli/mas-ctl.md).

## Path variable reference

| Symbol | Default layout | Role |
|--------|----------------|------|
| `--8<-- "includes/mas-paths.md:workspace-config-filename"` | project root | Workspace config (`paths:`, `infra_refs:`, …) |
| `$XDG_CONFIG_HOME` | `~/.config` | Base for user config (see row below) |
| `--8<-- "includes/mas-paths.md:xdg-user-config"` | under `$XDG_CONFIG_HOME` | Global config fallback |
| `$XDG_DATA_HOME` | `~/.local/share` | Base for persistent lab data |
| `--8<-- "includes/mas-paths.md:xdg-labs-dir"` | under `$XDG_DATA_HOME` | Benchmark / lab output root |
| `--8<-- "includes/mas-paths.md:xdg-runs-dir"` | under `$XDG_DATA_HOME` | Agent session run folders |
| `--8<-- "includes/mas-paths.md:mas-home"` | under `$XDG_DATA_HOME` | Controller `MAS_HOME` default |
| `--8<-- "includes/mas-paths.md:controller-socket"` | under `$XDG_DATA_HOME` | Controller Unix socket |
| `--8<-- "includes/mas-paths.md:xdg-agent-memory"` | under `$XDG_DATA_HOME` | Semantic memory SQLite (overlays) |
| `$XDG_CACHE_HOME` | `~/.cache` | Base for caches |
| `--8<-- "includes/mas-paths.md:xdg-trace-cache"` | under `$XDG_CACHE_HOME` | Content-addressed trace cache |
| `--8<-- "includes/mas-paths.md:xdg-artifacts-cache"` | under `$XDG_CACHE_HOME` | Pipeline step cache |
| `--8<-- "includes/mas-paths.md:xdg-llm-cache"` | under `$XDG_CACHE_HOME` | LLM cache — built-in: [execution.md](manifests/execution.md#cache--the-llm-response-cache); infra: [llm-cache.md](manifests/llm-cache.md) · [ref](references/llm-cache.md) |
| `$XDG_STATE_HOME` | `~/.local/state` | Base for state files |
| `--8<-- "includes/mas-paths.md:xdg-last-run"` | under `$XDG_STATE_HOME` | Last benchmark run pointer |

MAS-Lab and `mas-ctl` resolve storage paths from the active config file
(see [Tutorial 0](tutorials/00-environment-setup/README.md)). Infra manifests
resolve from workspace refs, `$XDG_CONFIG_HOME/mas/infra/`, or explicit
`--infra-ref` paths.

`config.yaml` may also define top-level `aliases:` overrides for runtime plugin
resolution. See [runtime/docs/plugin-aliases.md](../runtime/docs/plugin-aliases.md)
for the discovery order and canonical name mapping.

**Config file names**

| Location | File | Role |
|----------|------|------|
| Project root | `--8<-- "includes/mas-paths.md:workspace-config-filename"` | Workspace config (`paths:`, `infra_refs:`, …) |
| User home | `--8<-- "includes/mas-paths.md:xdg-user-config"` | Global fallback when no project file is found |

Default data paths follow the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html):

| XDG variable | Default | MAS usage |
|--------------|---------|-----------|
| `XDG_CONFIG_HOME` | `~/.config` | `$XDG_CONFIG_HOME/mas/config.yaml`, `…/infra/` |
| `XDG_DATA_HOME` | `~/.local/share` | `$XDG_DATA_HOME/mas/labs`, `…/runs`, `…/data` |
| `XDG_CACHE_HOME` | `~/.cache` | `$XDG_CACHE_HOME/mas/traces`, `…/artifacts`, `…/llm_cache.json` |
| `XDG_STATE_HOME` | `~/.local/state` | `$XDG_STATE_HOME/mas/last-run.json` |

## Quick Start

### 1. Create user config directory

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/mas/infra"
```

For a self-contained project directory, initialize project-local configuration
instead of user-level configuration:

```bash
cd /path/to/project
mas-lab init --local
```

This writes `config.yaml` and `infra/<name>.yaml` below the project root. The
runtime discovers that workspace file before the XDG fallback, and Docker sees
the same files when the project is mounted at `/workspace`.

### 2. Install a default infra manifest (optional)

```bash
cp config/infra/openai.example.yaml "${XDG_CONFIG_HOME:-$HOME/.config}/mas/infra/default.yaml"
```

Workspace checkouts use the sample at
[`library-samples/sample-workspace/config.yaml`](../library-samples/sample-workspace/config.yaml)
(copy it to your project root; commands find it by walking up from the
current directory).

For first-time setup via `mas-lab init`, generated files come from templates
bundled in the `mas-lab` package:
[`lab/src/mas/lab/templates/init/config.yaml`](../lab/src/mas/lab/templates/init/config.yaml)
and [`lab/src/mas/lab/templates/infra/llmprovider.yaml`](../lab/src/mas/lab/templates/infra/llmprovider.yaml).

### 3. Set API key

```bash
export OPENAI_API_KEY=sk-...
```

### 4. Run without --infra-ref

```bash
# Uses workspace infra_refs or $XDG_CONFIG_HOME/mas/infra/default.yaml
mas-ctl chat agent.yaml -q "What is 2+2?"
```

### Human exchange log (`mas_ctl.trace`)

Stdout is the conversation. The AGENT↔LLM↔TOOL transcript is a **human** log on
stderr. Persist `mas_ctl.trace: summary` in `config.yaml` so you do not need
`--trace`. Color stays opt-in (`--trace-color` / `trace_color: true`).

Complete tables: [config.yaml](references/config.yaml.md#mas_ctl) ·
[mas-ctl flags](cli/mas-ctl.md#exchange-log).

## Configuration Discovery

The runtime searches for infra manifests in this order:

1. **CLI flag**: `--infra-ref <path>`
2. **Workspace**: `infra_refs` in `config.yaml`
3. **User default**: `$XDG_CONFIG_HOME/mas/infra/default.yaml` (if no CLI flag)

Runtime engine manifests (`kind: RuntimeEngine`) resolve via optional
`runtime_refs` in `config.yaml`, `--runtime-ref`, or user
`default_runtime` in `$XDG_CONFIG_HOME/mas/config.yaml`. They are **not**
declared on Agent or MAS manifests. Omit `runtime_refs` to use package defaults
only. See [runtime-engine.md](manifests/runtime-engine.md).

Model override for a single `mas-ctl chat` / `mas-ctl tui` run (overrides manifest
`spec.models`): `--model ID`, e.g. `gpt-4o-mini` on direct OpenAI, or a
provider-prefixed id (e.g. `azure/gpt-4o-mini`) through an OpenAI-compatible
proxy gateway. For MAS runs and benchmarks, declare models in the manifest or
pin them in the experiment (`model:` / `models:`).

### Data paths

Lab and benchmark output locations use the unified ladder documented in
`mas.lab.paths` (see `mas-lab config` for effective values). Set them under
`paths:` in `config.yaml` (`labs_dir`, `runs_dir`, `cache_dir`); the data root
is the parent of `labs_dir`.

When `paths.cache_dir` is set in `config.yaml`, trace cache defaults to
`<cache_dir>/traces`. Otherwise trace cache is `$XDG_CACHE_HOME/mas/traces`.

### Environment overrides (last resort)

Manifests, `config.yaml`, and CLI flags are the supported configuration
surface: they are versioned with the project and give the same result on
every machine. The variables below exist only as last-resort overrides for
test harnesses and one-off debugging. Do not put them in `.env` files or
shell profiles: they apply silently to every run in that environment,
including the long-lived controller daemon, which keeps the environment it
started with. Model and infra/runtime ref overrides log a warning when applied.

| Variable | Overrides |
|----------|-----------|
| `MAS_CTL_MODEL` / `MAS_LLM_MODEL` | `spec.models` (use `--model` or the experiment's `models:`) |
| `MAS_INFRA_REFS` / `MAS_RUNTIME_REFS` | Workspace `infra_refs` / `runtime_refs` (use `--infra-ref` / `--runtime-ref`) |
| `MAS_WORKSPACE_ROOT` | Workspace discovery from the current directory |
| `MAS_LABS_ROOT`, `MAS_RUNS_ROOT` | `paths.labs_dir`, `paths.runs_dir` |
| `MAS_DATA_ROOT` / `MAS_LAB_DATA` | Data root (derived from `paths.labs_dir`) |
| `MAS_TRACE_CACHE`, `MAS_DATA_CACHE` | Trace / pipeline step cache (use `--trace-cache` / `--data-cache`) |
| `MAS_LLM_CACHE`, `MAS_LLM_CACHE_READ` / `MAS_LLM_CACHE_WRITE` | Built-in engine cache — [execution.md](manifests/execution.md#cache--the-llm-response-cache) |
| `MAS_LLM_HTTP_RETRIES` | Extra LLM HTTP retries (`attempts = retries + 1`). Prefer `spec.control.retry.llm` — [reliability.md](references/reliability.md) |
| `MAS_LLM_HTTP_RETRY_BACKOFF` | LLM HTTP base backoff seconds (also disables jitter) |
| `MAS_HOME`, `MAS_CONTROLLER_SOCKET` | Controller data root / socket |

Secrets (`OPENAI_API_KEY`, proxy credentials) are the exception: they belong
in the environment, never in YAML.

Relative paths in any config file (`--8<-- "includes/mas-paths.md:workspace-config-filename"` or `--8<-- "includes/mas-paths.md:xdg-user-config"`)
resolve from **that file's directory** — e.g. with user config at
`~/.config/mas/config.yaml`, `labs_dir: custom/labs` → `~/.config/mas/custom/labs`.

## Doc authors

Recurring path strings live in `mas.runtime.constants` / `mas.runtime.xdg` and are
generated into [`includes/mas-paths.md`](includes/mas-paths.md) for MkDocs snippets.
After changing defaults, run `task docs-gen` and commit the updated include file.
Include a value in markdown with pymdownx snippets, for example
`--8<-- "includes/mas-paths.md:xdg-trace-cache"`.

### Resolution Rules

When resolving a library `name:path` ref (tools, overlays, infra bundles, …),
the prefix is always a **library name**. Lab-local libraries are searched
first, then workspace `manifest_libraries:`, then installed libraries.

List local library dirs in `lab-config.yaml` `lab.libraries` (and put
`library.yaml` in that dir). List extra checkouts in workspace
`config.yaml` `manifest_libraries:` (a list of paths; the name is the
directory stem).

User guide: [labs-and-libraries.md](labs-and-libraries.md). Search order and
`LookupError`: [library-discovery.md](library-discovery.md).

Infra files that are not `name:path` still fall through to `$XDG_CONFIG_HOME/mas/infra/{ref}` or a path relative to the manifest directory.

### Examples

```bash
# Workspace bundle ref
mas-ctl chat agent.yaml --infra-ref standard:openai -q "Hello"

# User config file
mas-ctl chat agent.yaml --infra-ref "$XDG_CONFIG_HOME/mas/infra/default.yaml" -q "Hello"

# Workspace-relative example file
mas-ctl chat agent.yaml --infra-ref config/infra/openai.example.yaml -q "Hello"
```

## Migrating older agent / MAS manifests

`mas-ctl validate` rejects infrastructure and runtime wiring on Agent, MAS, and
overlay patches, and rejects `spec.execution` on agents. Use this workspace file
instead:

| Removed from manifests | Use instead |
| --- | --- |
| `spec.infra_refs`, `spec.runtime_refs`, `infra_interceptors` | `infra_refs` / `runtime_refs` in `config.yaml`, `--infra-ref` / `--runtime-ref` |
| `spec.execution` (cache, stream, queue depth, parallel tools, …) | `kind: RuntimeEngine` refs (see [runtime-engine.md](manifests/runtime-engine.md)) |
| Offline LLM turns (no live provider) | [llm_cache replay](manifests/llm-cache.md) (`raise_on_miss`) recorded against a live provider |

`experiment.execution` in **mas-lab benchmark** YAML is unrelated — batch
orchestration and trace emulation ([experiment.md](manifests/experiment.md#execution-batch-orchestration)).

## Example Configurations

### OpenAI

See `library-standard/src/mas/library/standard/libs/standard/openai.yaml` and
`config/infra/openai.example.yaml`.

### Offline replay

Record with a live provider, then replay from disk (`raise_on_miss: true`).
See [llm-cache.md](manifests/llm-cache.md).

Library names, lab-local `lab.libraries`, and workspace `manifest_libraries:`:
[labs-and-libraries.md](labs-and-libraries.md).
