<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Contract Reference

This section documents the runtime contracts used by `mas-runtime`.
It is aimed at contributors implementing new plugins, runtime surfaces, or
MAS-facing facades.

## What belongs here

- A contract defines a stable runtime boundary.
- A plugin implements one or more contracts.
- The runtime calls contracts through direct method calls, hook dispatch,
  or registry-driven composition.

For taxonomy and selection guidance, start with [taxonomy.md](taxonomy.md).

## OSS vs design target

The table below lists the **full contract taxonomy** used in architecture docs. Only a subset
has Python protocol classes under `runtime/src/mas/runtime/contracts/` in this OSS release.

**Implemented in OSS** (importable today):

| Contract ID | Class |
| --- | --- |
| `tool` | `ToolContract` |
| `memory` | `MemoryContract` |
| `context` | `ContextContract` |
| `context_manager` | `ContextManagerContract` |
| `dp` | `DesignPatternPlugin` / `DesignPatternContract` |
| `engine` | `EngineContract` |
| `ctx_assembler` | `CtxAssembler` |
| `observability` | `ObservabilitySink` |
| `cm_factory` | `CMFactory` |

Rows below marked **design** are specified for extension authors but not exported as
standalone protocols yet.

## Contract inventory

| Contract ID | Class | Category | Purpose | Primary methods | Runtime calls through | Reference |
| --- | --- | --- | --- | --- | --- | --- |
| `tool` | `ToolContract` | Capability | External tool execution boundary | `list_tools()`, `call_tool()` | `collect_tools`, `execute_tool`, `pre_tool_call`, `post_tool_call` | [model-and-tools.md](model-and-tools.md#toolcontract) |
| `prompt` | `PromptContract` | Capability | Prompt template retrieval | `fetch_prompt()` | `pre_prompt_build`, `post_prompt_build` | [model-and-tools.md](model-and-tools.md#promptcontract) |
| `memory` | `MemoryContract` | Capability | Semantic, episodic, and procedural memory I/O | `read_memory()`, `write_memory()` | `pre_memory_store`, `post_memory_store` | [model-and-tools.md](model-and-tools.md#memorycontract) |
| `model_access` | `ModelAccessContract` | Capability | Provider-backed model execution | `on_collect_models()`, `complete()` | `collect_models`, `pre_llm_call`, `post_llm_call` | [model-and-tools.md](model-and-tools.md#modelaccesscontract) |
| `sensor` | `SensorContract` | Capability | Normalize inbound signals into runtime events | `pull()`, `emit_event()`, `push_reply()` | `pre_sensor_event`, `post_sensor_event` | [messaging-and-orchestration.md](messaging-and-orchestration.md#sensorcontract) |
| `message` | `MessageContract` | Capability | Simple inter-agent messaging | `send_message()`, `receive_message()` | `pre_agent_communication`, `post_agent_communication` | [messaging-and-orchestration.md](messaging-and-orchestration.md#messagecontract) |
| `transport` | `TransportContract` | Capability | Physical delivery channel for inter-agent traffic | `start()`, `stop()`, `send()` | Transport injected into messaging plugins | [messaging-and-orchestration.md](messaging-and-orchestration.md#transportcontract) |
| `recorder` | `RecorderContract` | Capability | Structured event recording | `emit()`, `flush()`, `close()` | Observability and audit emission | [execution-control-and-observability.md](execution-control-and-observability.md#recordercontract) |
| `control` | `ControlContract` | Capability | Pause, resume, abort, steer, checkpoint | `pause()`, `resume()`, `abort()`, `checkpoint()`, `restore_checkpoint()`, `steer()` | Control plane and hook-time interventions | [execution-control-and-observability.md](execution-control-and-observability.md#controlcontract) |
| `session` | `SessionContract` | Capability | Durable per-contact conversational state | `load_session()`, `save_session()`, `list_sessions()` | `pre_session_access`, `post_session_access` | [state-and-context.md](state-and-context.md#sessioncontract) |
| `execution` | `ExecutionSessionContract` | Capability | Durable checkpointing of in-flight execution state | `checkpoint()`, `load_execution()`, `latest_execution()` | `on_pre_checkpoint`, `on_post_checkpoint`, `on_pre_restore`, `on_post_restore` | [state-and-context.md](state-and-context.md#executionsessioncontract) |
| `shared_context` | `SharedContextContract` | Capability | Multi-agent shared state and coordination | `get()`, `set()`, `watch()`, `acquire_lock()` | Shared coordination surfaces | [state-and-context.md](state-and-context.md#sharedcontextcontract) |
| `context` | `ContextContract` | Capability | Typed prompt context contribution | `collect_context()` | `collect_context` aggregation | [state-and-context.md](state-and-context.md#contextcontract) |
| `context_manager` | `ContextManagerContract` | Supporting interface | Conversation-history trimming and summarization | `manage_history()` | Invoked by context assembly / history management | [state-and-context.md](state-and-context.md#contextmanagercontract) |
| `delegation` | `DelegationContract` | Capability | Expose agents as tools and prompt-visible delegates | `list_tools()`, `call_tool()`, `delegate()`, `collect_context()` | Tool collection, tool execution, context assembly, agent communication hooks | [messaging-and-orchestration.md](messaging-and-orchestration.md#delegationcontract) |
| `workflow` | `WorkflowContract` | Orchestration | MAS execution topology boundary | `run()` | Runtime-selected workflow driver | [messaging-and-orchestration.md](messaging-and-orchestration.md#workflowcontract) |
| `budget` | `BudgetTracker` (OSS) / `BudgetContract` (design) | Governance | Token, cost, and call ceilings | `check_*`, overlay `budget_threshold` | LLM and tool governance hooks | [governance.md](governance.md#budgetcontract) |
| `sandbox` | *(internal — mas-lab-internal)* | — | — | — | — | — |
| `tbac` | *(internal — mas-lab-internal)* | — | — | — | — | — |
| `routing` | `RoutingContract` | Governance | Agent-to-agent edge policy | `check()` | Routing and delegate visibility policy | [governance.md](governance.md#routingcontract) |
| `dp` | `DesignPatternContract` | Capability | Design-pattern realizability over the runtime hook basis | `start()`, `next_action()`, `on_action_result()`, `should_continue()` | `pre_execution`, `post_llm_call`, `post_tool_call`, lifecycle checks | [design-patterns.md](design-patterns.md#designpatterncontract) |
| `evolution` | *(internal — not in OSS)* | — | — | — | — | — |
| `surface` | `SurfaceAdapter` | Capability | Multi-surface channel adapter (Slack, web, CLI, agent-remote) | `ingest()`, `deliver()`, `start()`, `stop()` | Surface lifecycle + hook bridge | [plugin-and-tool-authoring.md](../../plugin-and-tool-authoring.md#surfaceadapter-multi-surface) |

## Recommended reading order

1. [taxonomy.md](taxonomy.md)
2. [model-and-tools.md](model-and-tools.md)
3. [state-and-context.md](state-and-context.md)
4. [messaging-and-orchestration.md](messaging-and-orchestration.md)
5. [execution-control-and-observability.md](execution-control-and-observability.md)
6. [governance.md](governance.md)
7. [design-patterns.md](design-patterns.md)
8. [mealy-hooks-and-closure.md](mealy-hooks-and-closure.md)

## Common call paths

### Tool execution

```text
LLM/tool planner
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

### Delegation and MAS orchestration

```text
WorkflowContract.run()
  -> DelegationContract.collect_context()
  -> DelegationContract.list_tools()
  -> RoutingContract.check()
  -> DelegationContract.delegate()
  -> MessageContract.send_message() or TransportContract.send()
```
