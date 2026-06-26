<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# CLI Reference Guide

Complete reference for **`mas-ctl`** (agents, compose) and **`mas-lab`** (benchmarks).

`mas-runtime` is a **library only** (no CLI). Use `mas-ctl chat` for single-agent runs.

## mas-ctl CLI

Control plane: compose MAS, chat with agents, validate manifests. Instantiates `mas.runtime` kernels.

### Installation

```bash
pip install mas-ctl mas-runtime
# or monorepo:
uv pip install -e runtime -e ctl
```

### Main commands

#### `chat` — Run an agent (interactive or scripted)

```bash
mas-ctl chat <manifest> [-q <text> ...] [-o <overlay.yaml> ...]
```

| Option | Description |
| --- | --- |
| `-q` / `--query` | Scripted input (repeat for multi-turn) |
| `-o` / `--overlay` | Overlay YAML (repeatable) |
| `-v` | Verbose logging |

#### `validate` — Check manifests

```bash
mas-ctl validate <manifest> [-o <overlay>] [--strict / --no-strict]
```

#### `run-mas`, `compose`, `plan` — Multi-agent

See `mas-ctl --help` and [ctl/README.md](../../../../ctl/README.md).

**OSS placement:** `local-inproc` only. Docker/Kubernetes placement is planned for a future release.

---

## mas-runtime (library — no CLI)

Embed the Mealy kernel via `RuntimeBuilder` or `mas.ctl.session.bootstrap`. See [mas-runtime-api.md](../api-reference/mas-runtime-api.md).

Legacy tutorial commands using `mas-runtime run-agent` should use **`mas-ctl chat`** (scenario tests rewrite automatically).

---

## mas-lab CLI

Experiment benchmarking and analysis.

### Installation

```bash
pip install mas-lab
# or
uv pip install mas-lab
```

### Main Commands

#### `benchmark` — Run experiments

```bash
mas-lab benchmark run <experiment.yaml> [OPTIONS]
```

| Option | Type | Description |
| --- | --- | --- |
| `<experiment.yaml>` | file | Experiment definition |
| `--output` | dir | Output directory (default: `./.mas-lab-output`) |
| `--flavour` | string | Override benchmark flavour |
| `--runs` | int | Override runs per scenario |
| `--workers` | int | Parallel workers (default: 4) |
| `--resume` | benchmark_id | Resume interrupted benchmark |
| `--verbose` | flag | Enable debug logging |
| `--timeout` | int | Timeout per run (seconds) |

Examples:

```bash
# Run experiment
mas-lab benchmark run experiment.yaml

# With custom settings
mas-lab benchmark run experiment.yaml \
  --workers 8 \
  --runs 5 \
  --timeout 120

# Override flavour
mas-lab benchmark run experiment.yaml --flavour gpt4

# Resume
mas-lab benchmark run experiment.yaml --resume cdf7f49b
```

#### `list` — List benchmark runs

```bash
mas-lab benchmark list [--limit 20]
```

Show recent benchmarks.

```bash
mas-lab benchmark list --limit 10
```

#### `show` — Inspect benchmark details

```bash
mas-lab benchmark show <benchmark_id>
```

Display full benchmark metadata and metrics summary.

```bash
mas-lab benchmark show cdf7f49b
```

#### `step` — Manage pipeline steps

```bash
mas-lab benchmark step list <benchmark_id>
mas-lab benchmark step show <benchmark_id> <step_id>
mas-lab benchmark step restart <benchmark_id> <step_id>
```

Examples:

```bash
# List steps in a benchmark
mas-lab benchmark step list cdf7f49b

# Show details of compute_metrics step
mas-lab benchmark step show cdf7f49b compute_metrics

# Rerun a failed step
mas-lab benchmark step restart cdf7f49b compute_metrics
```

#### `check` — Validate experiment

```bash
mas-lab check <experiment.yaml> [--verbose]
```

Validates experiment definition without running.

```bash
mas-lab check experiment.yaml -v
```

#### `demo` — Interactive UI demo

```bash
mas-lab demo [use_case] [--port 8080]
```

Launch interactive demo for a lab use case.

```bash
mas-lab demo trip-planner
mas-lab demo trip-planner --port 8088
mas-lab demo  # list available use cases
```

---

## Environment Variables

### API Keys

All tools read secrets from environment variables:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Vertex AI (uses default credentials)
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"

# Azure OpenAI
export AZURE_OPENAI_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://..."
```

### Tool Configuration

```bash
# Agent runtime debug
export MAS_DEBUG=1
export MAS_LOG_LEVEL=debug

# Lab output (runs and artefacts)
export MAS_DATA_ROOT="${MAS_DATA_ROOT:-$HOME/.mas}"
export MAS_RUNS_ROOT="${MAS_RUNS_ROOT:-$MAS_DATA_ROOT/runs}"

# MAS controller
export MAS_NAMESPACE=production
export MAS_CONTROLLER_URL=http://localhost:8080
```

---

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | General error |
| `2` | Usage error (bad arguments) |
| `3` | Timeout |
| `4` | Not found |
| `5` | Validation failed |

---

## Examples & Workflows

### Run Agent in Batch Mode

```bash
for input in "What is AI?" "How do transformers work?" "Explain GANs"; do
  mas-runtime run-agent agent.yaml --input "$input" --format json >> results.jsonl
done
```

### Compare Models

```bash
mas-lab benchmark run experiment.yaml --flavour gpt4
mas-lab benchmark run experiment.yaml --flavour claude

# Later: compare results in Python
from mas.lab.labs import Lab
lab = Lab()
```

For more details, see:

- [mas-runtime API Reference](../api-reference/mas-runtime-api.md)
- [mas-lab API Reference](../api-reference/mas-lab-api.md)
