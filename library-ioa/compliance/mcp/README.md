# MCP Compliance

This directory contains the reproducible MCP protocol-compliance entry point.
Generated reports stay outside Git and are uploaded by CI as workflow artifacts.

## Prerequisites

- Python 3.11 or newer
- `uv`
- `go-task` (`task`)
- Node.js with `npx`
- Network access for the pinned `@modelcontextprotocol/conformance` runner

Detailed installation steps are in [INSTALL.md](INSTALL.md). The expected
report layout and CI retention policy are documented in [RESULTS.md](RESULTS.md).

## Install

From the repository root:

```bash
task --dir library-ioa/compliance/mcp install
```

The dedicated task creates or reuses `.venv` and installs only the editable
packages required by the fixture. It is non-interactive when `.venv` already
exists. The equivalent uv-only commands are:

```bash
uv venv .venv --allow-existing
uv pip install -e runtime -e library-ioa
uv pip install pytest pytest-asyncio
```

## Run both revisions

```bash
MCP_CONFORMANCE_RESULTS="$PWD/library-ioa/compliance/mcp/results" \
  ./library-ioa/compliance/mcp/mcp-conformance.sh
```

The command starts the deterministic MCP fixture, runs the pinned official
runner separately for `2025-11-25` and `2026-07-28`, and shuts the fixture down.
Reports are written below `library-ioa/compliance/mcp/results/` as JSON. The directory is
ignored locally and must not be committed.

The same run is available through the dedicated compliance Taskfile:

```bash
task --dir library-ioa/compliance/mcp run
```

Override the runner or output directory without editing the repository:

```bash
MCP_CONFORMANCE_VERSION=0.2.0-alpha.11 \
MCP_CONFORMANCE_RESULTS=/tmp/mas-mcp-conformance \
  task --dir library-ioa/compliance/mcp run
```

Validate the shell runner, Taskfile, workflows, and focused fixture tests:

```bash
task --dir library-ioa/compliance/mcp validate-config
task --dir library-ioa/compliance/mcp test
```

## CI and releases

The pull-request and main-branch test workflow runs this command and uploads
`mcp-compliance-${GITHUB_SHA}`. The package-publish workflow runs it for release
tags and uploads `mcp-compliance-${GITHUB_REF_NAME}` with a 90-day retention.
The artifact contains the machine-readable runner output and is the compliance
record for that workflow run.

The current pinned runner is `@modelcontextprotocol/conformance@0.2.0-alpha.11`.
Both revisions are required to pass all scored server checks; runner-owned skips
and informational warnings remain visible in the JSON output.
