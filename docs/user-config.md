<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# User-Level Configuration

Canonical path variables and their defaults live on this page. In other docs,
prefer **`$XDG_*` / `MAS_*` names** (not hardcoded home paths). MkDocs tutorials
can include values via
[`includes/mas-paths.md`](includes/mas-paths.md) snippets (`task docs-gen`).

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
| `$XDG_STATE_HOME` | `~/.local/state` | Base for state files |
| `--8<-- "includes/mas-paths.md:xdg-last-run"` | under `$XDG_STATE_HOME` | Last benchmark run pointer |
| `MAS_LABS_ROOT` | — | Env override for labs root |
| `MAS_RUNS_ROOT` | — | Env override for runs root |
| `MAS_DATA_ROOT` / `MAS_LAB_DATA` | — | Env override for data root |
| `MAS_TRACE_CACHE` | — | Env override for trace cache |
| `MAS_DATA_CACHE` | — | Env override for pipeline cache |
| `MAS_HOME` | `--8<-- "includes/mas-paths.md:mas-home"` | Env override for controller data root |
| `MAS_CONTROLLER_SOCKET` | `--8<-- "includes/mas-paths.md:controller-socket"` | Env override for controller socket |

MAS-Lab and `mas-ctl` resolve storage paths from the active config file
(see [Tutorial 0](tutorials/00-environment-setup/README.md)). Infra manifests
resolve from workspace refs, `$XDG_CONFIG_HOME/mas/infra/`, or explicit
`--infra-ref` paths.

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
| `XDG_CACHE_HOME` | `~/.cache` | `$XDG_CACHE_HOME/mas/traces`, `…/artifacts` |
| `XDG_STATE_HOME` | `~/.local/state` | `$XDG_STATE_HOME/mas/last-run.json` |

## Quick Start

### 1. Create user config directory

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/mas/infra"
```

### 2. Install a default infra manifest (optional)

```bash
cp config/infra/openai.example.yaml "${XDG_CONFIG_HOME:-$HOME/.config}/mas/infra/default.yaml"
```

Workspace checkouts use the sample at
[`examples/sample-workspace/config.yaml`](../examples/sample-workspace/config.yaml)
(`MAS_WORKSPACE_ROOT` is set automatically in pytest; copy to your project root
or export `MAS_WORKSPACE_ROOT` for local CLI runs).

### 3. Set API key

```bash
export OPENAI_API_KEY=sk-...
```

### 4. Run without --infra-ref

```bash
# Uses workspace infra_refs or $XDG_CONFIG_HOME/mas/infra/default.yaml
mas-ctl chat agent.yaml -q "What is 2+2?"
```

## Configuration Discovery

The runtime searches for infra manifests in this order:

1. **CLI flag**: `--infra-ref <path>`
2. **Environment**: `MAS_INFRA_REFS` (comma-separated; overrides workspace `infra_refs`)
3. **Workspace**: `infra_refs` in `config.yaml`
4. **User default**: `$XDG_CONFIG_HOME/mas/infra/default.yaml` (if no CLI flag)

Model override for a single `mas-ctl chat` / `run-mas` (overrides manifest `spec.models`):

- `MAS_CTL_MODEL` — e.g. `gpt-4o-mini` on direct OpenAI, or a provider-prefixed id (e.g. `azure/gpt-4o-mini`) when routing through an OpenAI-compatible proxy gateway
- `MAS_LLM_MODEL` — alias (common in `.env` files)

### Data paths

Lab and benchmark output locations use the unified ladder documented in
`mas.lab.paths` (see `mas-lab config` for effective values).

| Variable | Role |
|----------|------|
| `MAS_LABS_ROOT` | Override `labs_dir` |
| `MAS_RUNS_ROOT` | Override `runs_dir` |
| `MAS_DATA_ROOT` | Root for derived data paths (`data_dir`, trace cache when `cache_dir` is default) |
| `MAS_LAB_DATA` | Override `data_dir` directly |
| `MAS_TRACE_CACHE` | Override trace cache directory |
| `MAS_DATA_CACHE` | Override pipeline step cache directory |

When `paths.cache_dir` is set in `config.yaml`, trace cache defaults to
`<cache_dir>/traces`. Otherwise trace cache is `$XDG_CACHE_HOME/mas/traces`
(unless `MAS_DATA_ROOT` / `MAS_LAB_DATA` redirect via `data_dir/trace-cache`).

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

When resolving an infra reference (e.g., `--infra-ref openai.example.yaml`):

1. **Installed libraries** — Auto-registered via `mas.runtime.manifest_libraries` entry points
2. **Workspace paths** — `manifest_libraries` in `config.yaml` for checkout trees that are not installed
3. **User config** — `$XDG_CONFIG_HOME/mas/infra/{ref}`
4. **Relative path** — Resolve from manifest directory

### Examples

```bash
# Workspace bundle ref
mas-ctl chat agent.yaml --infra-ref standard:openai -q "Hello"

# User config file
mas-ctl chat agent.yaml --infra-ref "$XDG_CONFIG_HOME/mas/infra/default.yaml" -q "Hello"

# Workspace-relative example file
mas-ctl chat agent.yaml --infra-ref config/infra/openai.example.yaml -q "Hello"
```

## Example Configurations

### OpenAI

See `library-standard/src/mas/library/standard/libs/standard/openai.yaml` and
`config/infra/openai.example.yaml`.

### Mock / offline

Use `standard:mock-llm` for CI and tutorials (no network).
