<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# User-Level Configuration

MAS-Lab and `mas-ctl` use **`~/.mas/config.yaml`** for labs output, trace cache, and
defaults (see [Tutorial 0](tutorials/00-environment-setup/README.md)). Infra
manifests resolve from workspace refs, `~/.mas/infra/`, or explicit `--infra-ref`
paths.

Legacy note: some runtime paths also accept `~/.config/mas/`; prefer `~/.mas/`
for a single home-directory layout.

## Quick Start

### 1. Create user config directory

```bash
mkdir -p ~/.mas/infra
```

### 2. Install a default infra manifest (optional)

```bash
cp config/infra/openai.example.yaml ~/.mas/infra/default.yaml
```

Workspace checkouts use the sample at
[`examples/sample-workspace/mas-workspace.yaml`](../examples/sample-workspace/mas-workspace.yaml)
(`MAS_WORKSPACE_ROOT` is set automatically in pytest; copy to your project root
or export `MAS_WORKSPACE_ROOT` for local CLI runs).

### 3. Set API key

```bash
export OPENAI_API_KEY=sk-...
```

### 4. Run without --infra-ref

```bash
# Uses workspace infra_refs or ~/.mas/infra/default.yaml
mas-ctl chat agent.yaml -q "What is 2+2?"
```

## Configuration Discovery

The runtime searches for infra manifests in this order:

1. **CLI flag**: `--infra-ref <path>`
2. **Environment**: `MAS_INFRA_REFS` (comma-separated; overrides workspace `infra_refs`)
3. **Workspace**: `infra_refs` in `mas-workspace.yaml`
4. **User default**: `~/.mas/infra/default.yaml` (if no CLI flag)
5. **Legacy fallback**: `~/.config/mas/infra/default.yaml`

Model override for a single `mas-ctl chat` / `run-mas` (overrides manifest `spec.models`):

- `MAS_CTL_MODEL` — e.g. `gpt-4o-mini` on direct OpenAI, or a provider-prefixed id (e.g. `azure/gpt-4o-mini`) when routing through an OpenAI-compatible proxy gateway
- `MAS_LLM_MODEL` — alias (common in `.env` files)

### Data paths

Lab and benchmark output locations are controlled by two environment variables:

- `MAS_LABS_ROOT` — root directory for lab definitions (the `*.lab` folders).
- `MAS_DATA_ROOT` — root directory for run output, datasets, and caches. When set,
  all path resolvers (run store, trace cache, datasets) derive from it; otherwise
  they default under `~/.mas-lab/`.

### Resolution Rules

When resolving an infra reference (e.g., `--infra-ref openai.example.yaml`):

1. **Installed libraries** — Auto-registered via `mas.runtime.manifest_libraries` entry points
2. **Workspace paths** — `manifest_libraries` in `mas-workspace.yaml` for checkout trees that are not installed
3. **User config** — `~/.config/mas/infra/{ref}` or `~/.mas/infra/{ref}`
4. **Relative path** — Resolve from manifest directory

### Examples

```bash
# Workspace bundle ref
mas-ctl chat agent.yaml --infra-ref standard:openai -q "Hello"

# User config file
mas-ctl chat agent.yaml --infra-ref ~/.mas/infra/default.yaml -q "Hello"

# Workspace-relative example file
mas-ctl chat agent.yaml --infra-ref config/infra/openai.example.yaml -q "Hello"
```

## Example Configurations

### OpenAI

See `library-standard/src/mas/library/standard/libs/standard/openai.yaml` and
`config/infra/openai.example.yaml`.

### Mock / offline

Use `standard:mock-llm` for CI and tutorials (no network).
