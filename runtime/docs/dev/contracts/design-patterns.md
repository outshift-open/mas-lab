<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Design Pattern Contract

This document covers `DPContract`, the runtime boundary used to make
agent design patterns realizable over the hook basis and state machine.

## DPContract

`DPContract` defines the lifecycle for a reasoning pattern such as
ReAct, Plan-and-Execute, Reflection, or Tree-of-Thoughts.

### DPContract purpose

- initialize design-pattern state
- derive the next action from current state and new input
- update state after tool execution
- determine when the pattern terminates

### DPContract vs Mealy state

This is the most important distinction to keep clear.

`DPContract` does **not** replace the Mealy machine.

Instead:

- the Mealy machine owns runtime execution states such as idle, reasoning,
  acting, interrupted, or terminated
- the design pattern owns the reasoning phase within that execution lifecycle

In practice:

- Mealy state answers: what kind of runtime step is happening?
- DP phase answers: what reasoning phase is the pattern currently in?

So a design pattern is not a second runtime kernel. It is a reasoning-policy
layer executed inside the runtime lifecycle.

### v0.1 kernel API (shipped)

The production kernel invokes design-pattern plugins through:

| Method | Role |
|--------|------|
| `handle_event(q, run, event, config)` | React to ingress (`UserInputReceived`, tool results, …) |
| `evaluate_next` / `_evaluate` | After engine I/O, schedule next egress (`LLM_CALL`, `TOOL_CALL`, client response) |
| `protocol_lines(q)` | Inject phase-specific system instructions into context |

Legacy hook-era names (`start`, `next_action`, `on_action_result`) describe the
**contract correspondence** below; new plugins should implement the kernel
methods on `ReactPlugin` subclasses.

### DPContract primary methods (hook correspondence)

| Method | Parameters | Notes |
| --- | --- | --- |
| `dp_id` | property | Stable pattern identifier |
| `start(context)` | initial context dict | Initializes `DPState` (hook: `pre_execution`) |
| `next_action(state, input_data)` | current state, LLM output or observation | Maps to post-LLM scheduling |
| `on_action_result(state, action, result)` | state, action, tool result | Maps to post-tool scheduling |
| `should_continue(state)` | current state | Termination predicate |
| `on_tool_error(state, tool_name, error, available_tools)` | state and error context | Optional recovery path |
| `on_policy_denial(state, contract_id, reason, denied_action, details)` | state and denial context | Optional — receive a governance denial as a signal instead of a crash; default re-raises |
| `messages` | property | Mutable message history |

### DPContract runtime mapping

The current contract documentation maps design-pattern operations to the hook
basis as follows:

| DP operation | Runtime hook or boundary |
| --- | --- |
| `start()` | `pre_execution` |
| `next_action()` | `post_llm_call` |
| `on_action_result()` | `post_tool_call` |
| `on_tool_error()` | `tool_call_error` |
| `on_policy_denial()` | `governance_denied` |
| `should_continue()` | lifecycle control check |

This mapping should be read as **architectural correspondence**, not as proof
that a design pattern owns the entire loop.

The intended control split is:

- the runtime owns the loop and chokepoints
- hooks expose those chokepoints
- the design pattern injects phase logic at those points

### DPContract core mental model

If you want the shortest possible model, think about the contract this way:

1. `start()` creates the initial DP state
2. `next_action()` decides what happens next
3. `on_action_result()` learns from the action result
4. `should_continue()` decides whether the reasoning pattern continues
5. `on_tool_error()` defines the recovery semantics

That is enough for most patterns. Anything beyond that should be treated
carefully, because it risks turning the design pattern into an owner of the
whole runtime loop.

### DPContract core state objects

The contract operates on these main types:

- `DPState`
- `DPAction`
- `DPPhase`

### What DPContract should not own

The contract should not become a dumping ground for unrelated concerns.

It should not own:

- model-provider selection
- sandbox or budget policy
- session persistence
- MAS topology or delegation routing
- UI behavior

Those belong to model, governance, session, orchestration, and facade layers.

### DPContract example

```python
from mas.runtime.contracts import DPContract, DPAction, DPPhase, DPState


class SingleStepAnswer(DPContract):
    @property
    def dp_id(self) -> str:
        return "dp:single-step@v1"

    def start(self, context):
        return DPState(current_phase=DPPhase.DECIDE, step_id=0, memory={})

    def next_action(self, state, input_data):
        return DPAction(action_type="finalize", phase=DPPhase.FINALIZE)

    def on_action_result(self, state, action, result):
        return state

    def should_continue(self, state):
        return False
```

## When to use DPContract

Use `DPContract` when the feature changes the reasoning lifecycle of
an agent. Do not use it for:

- provider selection
- tool policy
- run topology
- session storage

Those belong to model, governance, orchestration, and session contracts.
