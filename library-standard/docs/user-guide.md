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
- Overlays (`observability-native`, `with-hardened`) — [index](../src/mas/library/standard/overlays/README.md)
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

### Overlays

Index: [src/mas/library/standard/overlays/README.md](../src/mas/library/standard/overlays/README.md).

| Overlay | Apply |
|---------|--------|
| `observability-native` | native `events.jsonl` |
| `with-hardened` | append `gov_no_undeclared_tool` |
| `cheap-summarizer` | `summarizer.params.model: gpt-4o-mini` |

```bash
mas-ctl chat agent.yaml \
  -o pkg://mas.library.standard/overlays/with-hardened.yaml \
  -o pkg://mas.library.standard/overlays/observability-native.yaml
```

CLI shortcut `--events` is equivalent to `observability-native` for one run.
Full flag matrix: [docs/cli/observability.md](../../docs/cli/observability.md).

### Add governance controls

Enable budget and policy plugins to constrain calls, tokens, or tool access.

Refuse tool names the model was not given in this LLM call's `tools` list
(even if they appear on the agent spec) with `with-hardened`, or list the
plugin on the governance *chain* (`spec.observability` is a sequence;
`spec.governance` is not — BLOCK stops, ALLOW continues):

```yaml
governance:
  - gov_no_undeclared_tool
```

Feature example (not a sample app):
[examples/governance/undeclared-tool/](../examples/governance/undeclared-tool/).
Index: [examples/](../examples/README.md).
Card: [no-undeclared-tool.md](../src/mas/library/standard/plugins/governance/no-undeclared-tool.md).

```bash
mas-ctl validate library-standard/examples/governance/undeclared-tool/agent.yaml
mas-ctl chat library-standard/examples/governance/undeclared-tool/agent.yaml \
  -q "Investigate the latency spike for payment-service."
```

### Override the history summarizer

Default `summarising` + `summarizer: llm` uses the agent model and a package
system prompt. Compaction fires on the **token budget**, not that prompt.

```yaml
context_manager:
  type: summarising
  params:
    summarizer:
      type: llm
      params:
        model: gpt-4o-mini
        instructions: |
          Preserve city names and dates. One paragraph.
```

Feature example (not a sample app):
[examples/context/summarizer-override/](../examples/context/summarizer-override/).
Card: [summarizer.md](../src/mas/library/standard/plugins/context/summarizer.md).
Docs: [summarization.md](../../docs/manifests/summarization.md).

```bash
mas-ctl validate library-standard/examples/context/summarizer-override/agent.yaml
mas-ctl chat library-standard/examples/context/summarizer-override/agent.yaml -v \
  -q "We fly to Lyon on 12 May."
```

Or overlay: `-o pkg://mas.library.standard/overlays/cheap-summarizer.yaml`.

### Add reasoning patterns

Apply design-pattern plugins (CoT/ReAct/plan-execute/introspection) via overlays.

- Plugin not found: verify package installation and manifest module path.
- Tool schema mismatch: check ToolContract input types and field names.
- Unexpected behavior: inspect active plugin order and overlay precedence.
