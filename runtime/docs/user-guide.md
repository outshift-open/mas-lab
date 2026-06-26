<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-runtime User Guide

`mas-runtime` is the single-agent execution runtime of MAS Lab. It provides contract-driven execution, plugin composition, hook-based governance, and overlay-based design patterns.

## Who this guide is for

- Application teams integrating one agent with tools and memory
- Platform teams enforcing policy and observability
- Experiment teams needing deterministic runtime behavior

## Install

```bash
uv pip install -e "runtime[all]"
```

## Quickstart

1. Create an `agent.yaml` manifest with model and plugin declarations.
2. Run the agent:

```bash
mas-runtime run-agent agent.yaml --interactive
```

1. Switch deployment profile with a flavour:

```bash
mas-runtime run-agent agent.yaml --flavour local
```

## Core concepts

- Contracts: Message, Tool, State, Control, Recorder
- Hooks: pre/post phases around LLM, tools, and state updates
- Plugins: declarative extensions loaded from manifests
- Overlays: additive configuration for reasoning patterns and environment variations

## Common tasks

### Add a tool

- Register a `ToolContract` implementation in manifest or builder path.
- Ensure input schema fields are documented and validated.

### Enable memory

- Use memory plugins from standard or dedicated memory libraries.
- Configure persistence path/backend through flavour or plugin config.

### Apply reasoning pattern

- Add a design-pattern overlay (for example CoT or ReAct).
- Validate behavior with controlled prompts before production rollout.

## Recommended docs

- `docs/index.md`
- `docs/contracts-reference.md`
- `docs/plugin-and-tool-authoring.md`
- `docs/dev/contracts/mealy-hooks-and-closure.md`
- `docs/plugin-flavours.md`
- `docs/design-patterns.md`

## Troubleshooting

- Missing plugin: verify module path and package install scope.
- Missing secret: ensure env var exists and is referenced by name.
- Unexpected tool calls: inspect governance plugin policy and trace output.

## Production checklist

- Flavour configured for target environment
- Governance policy enabled and tested
- Telemetry spans emitted and export path validated
- Integration tests cover failure paths and retries
