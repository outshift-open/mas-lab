<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 12 — Spawned subagents

> **Packages:** `mas-runtime`, `mas-ctl`
> **Prerequisite:** [Tutorial 0](../00-environment-setup/) and an Agent manifest
> runnable with the configured model.

Suppose a parent agent needs a second opinion on one narrow task — reviewing a
proposed change — without becoming a code reviewer itself and without the
operator having to write a new agent for every delegation. This tutorial
enables exactly that: the parent asks a temporary specialist to perform a
bounded task. The specialist is a pre-authored Agent manifest; the parent
cannot create new tools or prompts at runtime, only pick from the templates
its own manifest declares.

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

## How dispatch actually works

Declaring the tool and running it go through two different plugins:

- `SpawnSubagentTool` (library-standard) only **advertises** `spawn_subagent`
  to the model — it checks that the manifest allows spawning and lists at
  least one template, then builds the tool schema from the declared
  template ids. Its own `on_execute_tool` always fails closed; it never runs
  anything.
- `SubagentSpawner` (`ctl/src/mas/ctl/executor/subagent_spawner.py`) is what
  actually dispatches a call: it materializes the child from the resolved
  template, runs one turn, and tears the instance down — in both a
  synchronous `spawn()` and an async `aspawn()` form, wired to whichever tool
  dispatch path the engine takes for that call.

Before a template is ever runnable, `load_subagent_templates()` resolves each
`ref:` under the **parent manifest's own directory** (`containment_roots` /
`resolve_under_roots`) and schema-validates the result as an Agent manifest.
A template cannot point outside the parent's directory tree, and a malformed
child manifest is rejected before the model can call it — not after.

## Run and inspect

Validate the manifests, then ask the parent to delegate a specific review:

```bash
mas-ctl validate docs/tutorials/12-subagents/agent.yaml
mas-ctl chat docs/tutorials/12-subagents/agent.yaml \
  -q "Ask the reviewer to check this change: def add(a, b): return a + b"
```

The parent's own reply is what the reviewer template said, not a rewrite or
summary by the parent — that answer came from a separate instance with its
own `react` design pattern and model, materialized just for this call. Add
`--trace` to see the `spawn_subagent` tool call and its result as a distinct
exchange.

The ctl layer materializes the child, runs one turn, and returns its final text
as the tool result. It unregisters the child's communication endpoint and
removes the instance even when execution fails. When the run has shared
observability, child calls join that sink and retain the parent-call identity.

`SpawnLedger` enforces the spawn count and recursive depth at the execution
boundary. A child can spawn again only when its own manifest grants the
capability and lists templates; the session-wide ledger still governs the
whole tree. Both the sync and async dispatch paths share that ledger, so
concurrent siblings spawned from the same turn (e.g. through
`asyncio.gather`) are budgeted together and never cross-talk — each gets its
own working-memory registry and teardown.

## What you built

The parent gained a bounded "ask a specialist" capability without the
operator writing any new tool code: `reviewer.yaml` is an ordinary Agent
manifest, the same shape as `agent.yaml` itself, declared as a template
rather than wired into a MAS workflow. Swap in a different template —
a different model, prompt, or tool set — and the parent's own manifest
and prompt do not change.

## Reference material

- [Subagent manifests](../../manifests/subagents.md) — full `spawn_subagent`
  field reference and budget semantics.
- [Schema examples](../../references/schemas.md) — the canonical
  `subagent-agent.yaml` / `subagent-reviewer.yaml` pair this tutorial copies
  from.
- Next: [Tutorial 13 — Control attach and debug](../13-control-and-debug/)
  attaches to a running session from outside the process — including one a
  subagent is part of.