<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 7 — Spawned subagents

> **Packages:** `mas-runtime`, `mas-ctl`
> **Prerequisite:** [Tutorial 0](../00-environment-setup/) and an Agent manifest
> runnable with the configured model.

This tutorial enables an agent to ask a temporary specialist to perform a
bounded task. The specialist is a pre-authored Agent manifest; the parent
cannot create new tools or prompts at runtime.

## Declare a template

Declare the system tool with its templates and bounds — that one entry is the
whole contract:

```yaml
spec:
  tools:
    - kind: system
      name: spawn_subagent
      params:
        templates:
          - id: reviewer
            ref: ./reviewer.yaml
            description: Check a proposed change for defects.
        max_spawns: 8
        max_depth: 3
```

`reviewer.yaml` is a normal Agent manifest. It determines the child's prompt,
model, tools, and skills. The parent LLM can choose the template and write a
task, but cannot supply another manifest or bypass the budgets.

## Run and inspect

Run the example with the CLI and ask the parent to delegate a specific review:

```bash
mas-ctl validate docs/schemas/examples/subagent-agent.yaml
mas-ctl chat docs/schemas/examples/subagent-agent.yaml
```

The ctl layer materializes the child, runs one turn, and returns its final text
as the tool result. It unregisters the child's communication endpoint and
removes the instance even when execution fails. When the run has shared
observability, child calls join that sink and retain the parent-call identity.

`SpawnLedger` enforces the spawn count and recursive depth at the execution
boundary. A child can spawn again only when its own manifest grants the
capability and lists templates; the session-wide ledger still governs the
whole tree. Execution is synchronous in this release; concurrent fan-out is a
later async phase.