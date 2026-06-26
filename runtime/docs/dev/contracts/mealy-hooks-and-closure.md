<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Mealy, Hooks, and Contract Closure

This note explains how contracts, hooks, and the Mealy machine fit together
without turning the runtime into an unbounded taxonomy of contract types.

It also defines the target notion of **closure** for the runtime.

## Short answer

Having **5 chokepoints** does not mean the runtime can only have **5 contracts**.

The two concepts live at different levels:

- a **chokepoint** is a runtime execution site that every critical operation
  must pass through
- a **contract** is a typed protocol exposed to developers and implemented by
  plugins or facades

The clean model is:

```text
Mealy machine
  -> reaches a runtime chokepoint
  -> runtime dispatches hooks around that chokepoint
  -> one or more contracts participate at that chokepoint
```

## Why more contracts than chokepoints is normal

Several contracts can share the same chokepoint.

Examples:

- the tool chokepoint may involve `ToolContract`, `BudgetContract`, and HITL plugins
- the model chokepoint may involve `ModelContract`, `BudgetContract`,
  `RecorderContract`, and cache plugins
- the state chokepoint may involve `MemoryContract`, `SessionContract`,
  `ExecutionSessionContract`, and `SharedContextContract`

So the intended relationship is **many contracts to one chokepoint family**,
not one contract to one chokepoint.

## The five chokepoint families

The closure model is easiest to reason about if the runtime is reduced to five
families of mandatory chokepoints.

| Chokepoint family | Runtime meaning | Base operation |
| --- | --- | --- |
| Execution | Entering or leaving one runtime step or run | execution lifecycle |
| Model | Calling an LLM or model provider | `llm_call()` |
| Tool | Executing an external tool or action | `tool_call()` |
| Communication | Sending work or messages across agent boundaries | `send_message()` |
| State | Reading or mutating durable or shared state | `memory_read()`, `memory_write()` and higher-level state services |

In the current Python code, scheduled egress operations are executed through the
kernel envelope (`mas.runtime.kernel.envelope`) and engine IO
(`mas.runtime.engine`).

## The Mealy role

The Mealy machine should stay responsible for **execution lifecycle and state
transitions**, not for modeling every plugin API directly.

The practical interpretation is:

- the Mealy machine decides when the runtime is in execution, reasoning,
  acting, waiting, interrupted, or terminated states
- chokepoints are the places where those states interact with the outside world
  or durable state
- hooks make these crossings observable and governable
- contracts provide typed protocols for the participants at those crossings

That gives a clean separation:

| Concern | Role |
| --- | --- |
| Mealy machine | Execution-state evolution |
| Chokepoints | Mandatory runtime crossings |
| Hooks | Interception and observability around those crossings |
| Contracts | Developer-facing typed interfaces |

## Target closure model

The target architecture is **perfect closure**.

That means:

1. every critical side effect must pass through a canonical chokepoint
2. every chokepoint must dispatch the corresponding hooks
3. every plugin must interact with the runtime through contracts or runtime
   facades rather than direct concrete backends
4. bypassing a chokepoint is considered an architectural violation

In practice, perfect closure means that a future Rust runtime or a
multi-process gRPC runtime could enforce the same boundaries much more
strictly than Python can.

## What is currently enforceable vs aspirational

### Already in the right direction

- standard hook definitions exist in
  [src/mas/runtime/core/hooks.py](../../src/mas/runtime/core/hooks.py)
- hook dispatch is centralized in
  [src/mas/runtime/core/plugin_registry.py](../../src/mas/runtime/core/plugin_registry.py)
- the base runtime operations are visible in
  [src/mas/runtime/core/base_agent.py](../../src/mas/runtime/core/base_agent.py)
- design-pattern mapping to hooks and Mealy states is explicit in
  [src/mas/runtime/contracts/dp_contract.py](../../src/mas/runtime/contracts/dp_contract.py)

### Not yet perfectly closed in Python

- a plugin can still import and call a lower-level component directly
- not all stateful operations are forced through one single normalized state
  facade yet
- several domain-specific hooks still exist in parallel with the chokepoint
  model

So the current architecture is best described as **closure-oriented**, not yet
**perfectly closed**.

## Should we remove dedicated hooks and architectural conventions?

As a target direction: mostly yes.

The cleaner long-term model is:

- keep a small fixed set of chokepoint hooks
- let multiple contracts plug into those chokepoints
- avoid adding a dedicated hook every time a new feature appears

That does **not** mean every hook should disappear immediately. It means the
runtime should converge toward a small canonical set and treat any extra hook
as suspect until justified.

## Why memory is not just a tool call

Treating memory as a tool call would collapse two different semantics.

Memory has different properties from tools:

- it is part of the agent's internal or semi-internal state semantics
- it needs provenance and versioning semantics
- it often benefits from richer interpretability and replay semantics
- it is not just an external action; it changes what the agent knows or can
  later recall

So keeping `MemoryContract` distinct from `ToolContract` is a good idea.

In fact, if interpretability matters, memory should probably become **more**
semantically explicit, not less.

## The developer model

From a developer perspective, contracts remain useful because they are the
typed interface surface.

That is compatible with a small chokepoint model:

- developers program against contracts
- the runtime routes those contracts through a fixed set of chokepoints
- the Mealy machine and hooks stay internal execution machinery

This is exactly the direction that will transfer well to Rust processes
communicating through gRPC.

## Rule for new contracts

A new contract should exist only if all of the following are true:

1. it models a stable developer-facing protocol
2. it participates at one of the canonical chokepoints, or justifies a new one
3. it has at least two plausible implementations or backends
4. it cannot be expressed cleanly as a plugin, profile, or facade above an
   existing contract

If those conditions are not met, do not create a contract.

## Rule for new hooks

A new hook should exist only if at least one of these is true:

1. a canonical chokepoint currently lacks interception
2. the runtime cannot express a required policy or observability guarantee
   with the existing hook family
3. the hook corresponds to a state transition the Mealy machine must expose

Otherwise, prefer reusing an existing chokepoint hook.

## Practical conclusion

The clean target architecture is not:

- infinitely many contracts
- infinitely many hooks
- conventions that developers are merely asked to respect

The clean target architecture is:

- a small fixed set of chokepoints
- a bounded set of typed contracts that plug into them
- explicit tests that treat bypass paths as architectural failures
