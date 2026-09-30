# MCP compliance installation

This directory contains the reproducible MCP protocol-compliance workflow. The
fixture uses the production `library-ioa` MCP server factory; the official
protocol runner is downloaded by `npx` at the pinned version.

## Prerequisites

- Python 3.11 or newer
- `uv`
- Node.js and `npx`
- Network access to PyPI and npm on the first run

`go-task` is recommended for the complete workflow. The shell entry point also
works directly after installing the Python packages with the commands below.

## Install

From the repository root:

```bash
task --dir compliance install
```

The equivalent uv-only installation is:

```bash
uv venv .venv --allow-existing
uv pip install -e runtime -e library-ioa
uv pip install pytest pytest-asyncio
```

## Run locally

Run both pinned MCP requirement sets and write JSON reports under
`compliance/results/`:

```bash
MCP_CONFORMANCE_RESULTS="$PWD/compliance/results" \
  ./compliance/mcp-conformance.sh
```

Or use the dedicated Taskfile:

```bash
task --dir compliance run
```

Before running the suite, validate configuration and the focused fixture tests:

```bash
task --dir compliance validate-config
task --dir compliance test
```

The runner starts the deterministic fixture, executes the official conformance
suite for revisions `2025-11-25` and `2026-07-28`, and stops the fixture even
when a test fails. Override the runner version, server port, or output path with
`MCP_CONFORMANCE_VERSION`, `MCP_CONFORMANCE_PORT`, or
`MCP_CONFORMANCE_RESULTS`.

Generated reports are local evidence and are ignored by Git. CI uploads them as
workflow artifacts.
