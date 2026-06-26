<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Contracts Reference

This document is the high-level entry point for the contract system used by
`mas-runtime`.

If you need method signatures, parameters, call paths, and implementation
examples, use the dedicated developer reference in
[dev/contracts/index.md](dev/contracts/index.md).

## Purpose

Contracts define stable runtime boundaries.

They are used to:

- expose capabilities such as tools, models, sessions, and messaging
- enforce governance such as budget caps and routing policy
- control orchestration without coupling topology to plugins

## Taxonomy

The runtime uses three top-level contract families.

| Family | Meaning | Examples |
| --- | --- | --- |
| Capability | What the runtime can access or expose | `ToolContract`, `ModelAccessContract`, `SessionContract` |
| Orchestration | How control flows across agents | `WorkflowContract` |
| Governance | What is permitted | `BudgetContract`, `RoutingContract` (sandbox/TBAC: internal-only) |

For the taxonomy rationale, see [dev/contracts/taxonomy.md](dev/contracts/taxonomy.md).

## Contract inventory

The current developer reference covers these contract groups.

| Group | Coverage |
| --- | --- |
| Models, prompts, tools, memory | [dev/contracts/model-and-tools.md](dev/contracts/model-and-tools.md) |
| Sessions, execution checkpoints, shared context, prompt context | [dev/contracts/state-and-context.md](dev/contracts/state-and-context.md) |
| Sensors, messaging, transport, delegation, workflow | [dev/contracts/messaging-and-orchestration.md](dev/contracts/messaging-and-orchestration.md) |
| Control and recorder surfaces | [dev/contracts/execution-control-and-observability.md](dev/contracts/execution-control-and-observability.md) |
| Budget, routing | [dev/contracts/governance.md](dev/contracts/governance.md) |
| Design-pattern lifecycle | [dev/contracts/design-patterns.md](dev/contracts/design-patterns.md) |

## How contracts are used

Contracts are not the same thing as plugins.

- a contract defines a runtime boundary
- a plugin implements one or more contracts
- the runtime invokes contracts through direct method calls, hook dispatch,
  or registry-driven composition

## Typical call paths

### Tool execution

```text
Runtime or planner
  -> ToolContract.list_tools()
  -> BudgetContract.on_pre_tool_call()
  -> ToolContract.call_tool()
  -> RecorderContract.emit()
```

### Model execution

```text
Runtime
  -> ModelAccessContract.on_collect_models()
  -> BudgetContract.on_pre_llm_call()
  -> ModelAccessContract.complete()
  -> BudgetContract.on_post_llm_call()
  -> RecorderContract.emit()
```

### MAS orchestration

```text
SensorContract.pull() or emit_event()
  -> SessionContract.load_session()
  -> WorkflowContract.run()
  -> DelegationContract.list_tools() and collect_context()
  -> MessageContract.send_message() or TransportContract.send()
```

## Reading guide

Choose the starting point that matches your task.

| If you want to... | Start here |
| --- | --- |
| Understand the family split | [dev/contracts/taxonomy.md](dev/contracts/taxonomy.md) |
| Implement a tool or model provider | [dev/contracts/model-and-tools.md](dev/contracts/model-and-tools.md) |
| Work on sessions, memory boundaries, or prompt assembly | [dev/contracts/state-and-context.md](dev/contracts/state-and-context.md) |
| Work on delegation or MAS topology | [dev/contracts/messaging-and-orchestration.md](dev/contracts/messaging-and-orchestration.md) |
| Work on policy enforcement | [dev/contracts/governance.md](dev/contracts/governance.md) |
| Work on reasoning patterns | [dev/contracts/design-patterns.md](dev/contracts/design-patterns.md) |

## Notes

- `LLMContract` is currently treated as a backward-compatible alias of
  `ModelAccessContract`.
- `RoutingContract` exists as an abstract governance boundary but currently has
  no concrete implementation in the repository.
- `ContextManagerContract` is documented alongside state and context because it
  operates on conversation history, even though it is a supporting interface
  rather than a top-level taxonomy family.
