<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-library-standard User Guide

`mas-library-standard` provides reusable plugins, tools, and flavours for MAS runtime projects.

## What you get

- Design-pattern plugins (`dp_*`)
- Skills and tool providers (`sk_*`, `tool_*`)
- Context and memory plugins (`ctx_*`, `memory_*`)
- Observability and governance plugins (`obs_*`, `gov_*`)
- Transport and integration plugins (`tp_*`, `tool_server_*`)

## Install

```bash
uv pip install -e library-standard
```

## Typical usage

1. Install library package.
2. Reference plugin/tool module paths in agent manifest.
3. Activate optional overlays/flavours per environment.

## Shared tutorial tools

- `WebSearchTool`
- `VerifyFactTool`
- `GetAttractionsTool`
- `GetScheduleTool`

Use these for tutorials and integration smoke tests. App-specific samples should live in labs/apps, not in this library.

## Common tasks

### Enable memory behavior

Use standard memory plugins for workspace/session context and compaction hooks.

### Add governance controls

Enable budget and policy plugins to constrain calls, tokens, or tool access.

### Add reasoning patterns

Apply design-pattern plugins (CoT/ReAct/plan-execute/introspection) via overlays.

### Enable native observability (`events.jsonl`)

Apply the standard overlay (same as `library-samples/overlays/observability-native.yaml`):

```bash
mas-ctl chat agent.yaml -o library-samples/overlays/observability-native.yaml
# or from installed package:
# -o pkg://mas.library.standard/overlays/observability-native.yaml
```

CLI shortcut: `--events` on `mas-ctl chat` / `tui` / `run-mas`. Full flag matrix:
[docs/cli/observability.md](../../docs/cli/observability.md).

- Plugin not found: verify package installation and manifest module path.
- Tool schema mismatch: check ToolContract input types and field names.
- Unexpected behavior: inspect active plugin order and overlay precedence.
