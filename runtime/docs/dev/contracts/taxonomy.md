<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Contract Taxonomy

This document explains how contracts are classified and how to choose the
correct boundary for a new runtime feature.

## The three contract families

`mas-runtime` distinguishes three top-level contract families in
`mas.runtime.contracts.base`:

| Family | Meaning | Typical question | Examples |
| --- | --- | --- | --- |
| Capability | What the runtime can access or expose | What operation is available? | `ToolContract`, `ModelAccessContract`, `SessionContract` |
| Orchestration | How control flows across agents | How are agents invoked and stitched together? | `WorkflowContract` |
| Governance | What is allowed | Is this operation permitted right now? | `BudgetContract`, `RoutingContract` |

The split matters because it keeps runtime surfaces composable:

- capabilities stay reusable
- orchestration stays topology-focused
- governance stays cross-cutting

## Chokepoints vs contracts

One source of confusion is that the runtime can have **more contracts than
chokepoints** without being over-designed.

- chokepoints are runtime execution sites
- contracts are developer-facing protocols

Several contracts can legitimately share one chokepoint.

Examples:

- the tool chokepoint can host `ToolContract`, `BudgetContract`, and HITL plugins
- the model chokepoint can host `ModelAccessContract`, `BudgetContract`, and
  `RecorderContract`
- the state chokepoint can host `MemoryContract`, `SessionContract`, and
  `ExecutionSessionContract`

See [mealy-hooks-and-closure.md](mealy-hooks-and-closure.md) for the target
closure model.

## Contract vs plugin vs implementation

| Term | Meaning | Example |
| --- | --- | --- |
| Contract | Abstract runtime boundary | `ToolContract` |
| Plugin | Concrete runtime component implementing a contract | tool-server-backed tool provider |
| Implementation type | Data structure or helper used by a plugin | `SessionState`, `ExecutionSession`, `SandboxPolicy` |

## Selection guide

Use this table when introducing a new feature.

| If the feature is about... | Prefer... | Avoid... |
| --- | --- | --- |
| Accessing a resource or service | A capability contract | Encoding policy into the resource contract |
| Denying or constraining access | A governance contract | Embedding denials inside every tool or provider |
| Running agents in a different topology | An orchestration contract | Coupling loop behavior to a capability plugin |
| Prompt contribution | `ContextContract` | Ad hoc mutation of `messages[]` in many plugins |
| Conversation history trimming | `ContextManagerContract` | Overloading `SessionContract` |
| Durable run checkpoints | `ExecutionSessionContract` | Flattening run state into `SessionContract` |
| Cross-agent shared state | `SharedContextContract` | Abusing `MemoryContract` for coordination locks |

## Important separations

### Session vs execution vs memory vs shared context

| Boundary | Stores | Scope |
| --- | --- | --- |
| `SessionContract` | Durable conversation history and metadata | Contact or channel session |
| `ExecutionSessionContract` | In-flight run state and checkpoint data | Single run |
| `MemoryContract` | Semantic, episodic, or procedural memory | Agent memory layer |
| `SharedContextContract` | Multi-agent coordination state and locks | Group or MAS-level coordination |

### Context vs context manager

| Boundary | Role |
| --- | --- |
| `ContextContract` | Contributes typed context parts to prompt assembly |
| `ContextManagerContract` | Trims or compresses past turns before the next LLM call |

`ContextContract` says what should be present. `ContextManagerContract` says
how much historical conversation survives into the next turn.

## Hook-driven execution

Many contracts are called through hooks rather than direct runtime imports.

```text
Runtime event
  -> registry executes pre_* hooks
  -> capability contract method runs
  -> registry executes post_* hooks
```

Examples:

- `ToolContract.call_tool()` is typically surrounded by `pre_tool_call` and
  `post_tool_call`
- `ModelAccessContract.complete()` is typically surrounded by `pre_llm_call`
  and `post_llm_call`
- `SessionContract.load_session()` and `save_session()` are surrounded by
  session access hooks

## Example: wiring a minimal runtime surface

```python
from mas.runtime.contracts import (
    InMemorySessionStore,
    InMemoryExecutionStore,
    DummyMemoryStore,
    LocalSharedContext,
)

session_store = InMemorySessionStore()
execution_store = InMemoryExecutionStore()
memory_store = DummyMemoryStore()
shared_context = LocalSharedContext()
```

This wiring gives you four distinct boundaries with different semantics. None
of them should be collapsed into a single generic "state" object.
