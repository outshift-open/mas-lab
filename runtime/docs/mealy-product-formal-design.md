<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Formal Design: Agent as a Distributed Mealy Machine

**Date**: 2026-06-08  
**Status**: Companion — full `ContractInput` enum until ABI is generated from code  
**Reference**: `formal_governance_and_ops.md` §16.1, §19.4, §28

---

## 0. Distributed Mealy Machine — the unifying view

A MAS agent is a **distributed Mealy machine** whose global configuration is:

```
C = (Q_product, τ)
```

where:
- **Q_product** = `(q_dp, q_obs₁…ₘ, q_gov₁…ₙ, q_ctx, q_model, q_tool, q_mem, …)` — the product state, one component per sub-machine
- **τ** = `TransitionContext` — the shared tape (messages, parts, metadata, provenance_log)

Each input symbol `σ` drives a **joint transition**:

```
(Q_product, τ) --σ--> (Q_product', τ')
```

where:
- **Q_product'** = each sub-machine steps on `σ` (those with no transition stay in place)
- **τ'** = sub-machine outputs may **write** to the tape (e.g. `ctx` writes `messages[]`, `obs` appends to `provenance_log`)

The DP sub-machine is the **scheduler**: its output symbol on each step determines which input symbol is emitted next (THINK → emit `llm_*` envelope, ACT → emit `tool_*` envelope, FINALIZE → emit `agent_end`).

This is equivalent to a **distributed automaton** where:
- The product state is the **control plane** (what phase each dimension is in)
- The tape is the **data plane** (what content flows through)
- The DP is the **instruction pointer** (what happens next)

For a multi-agent system (MAS), the same model scales: each agent is one such distributed machine; the coordination contract routes symbols between agents.


An agent is a **synchronous product** of Mealy machines, one per contract dimension.
The product machine steps all sub-machines simultaneously on every input symbol.
Governance and observability are **not special cases** — they are sub-machines
registered in the product like any other dimension.

```
Agent = M_dp ⊗ M_ctx ⊗ M_cm ⊗ M_model ⊗ M_tool ⊗ M_mem
      ⊗ M_gov₁ ⊗ … ⊗ M_govₙ        (MULTIPLE_INSTANCE)
      ⊗ M_obs₁ ⊗ … ⊗ M_obsₘ        (MULTIPLE_INSTANCE)
```

The `⊗` operator is the **GuardedProductComposer**: all machines step on the
same input symbol, guards are evaluated, outputs are collected.

---

## 2. Contract Dimensions and Their Machines

Each contract in the taxonomy maps to one Mealy machine dimension:

| Dimension        | Contract(s)                               | Cardinality      | Role                                    |
|------------------|-------------------------------------------|------------------|-----------------------------------------|
| `dp`             | `DesignPatternContract`                   | SINGLE_INSTANCE  | Reasoning pattern (ReAct, CoT, etc.)    |
| `ctx`            | `ContextContract` | SINGLE_INSTANCE | Context assembly from all sources       |
| `cm`             | `ContextManagerContract` (trim/budget)    | SINGLE_INSTANCE  | Token budget enforcement on context     |
| `model`          | `ModelContract` / `LLMContract`           | SINGLE_INSTANCE  | LLM call                                |
| `tool`           | `ToolContract`                            | SINGLE_INSTANCE  | Tool execution                          |
| `memory`         | `MemoryContract`                          | SINGLE_INSTANCE  | Memory read/write                       |
| `transport`      | `TransportContract` / `MessageContract`   | SINGLE_INSTANCE  | Inter-agent messaging                   |
| `session`        | `ExecutionSessionContract`                | SINGLE_INSTANCE  | Durable session state                   |
| `coordination`   | `CoordinationContract`                    | SINGLE_INSTANCE  | Parallel tool barrier / fan-out         |
| `transformation` | (inline, no dedicated contract)           | SINGLE_INSTANCE  | Input/output transformation             |
| `governance`     | `GovernanceContract` (Budget, routing, …) | MULTIPLE_INSTANCE| Policy enforcement — applied to all     |
| `observability`  | `RecorderContract` / OTel                 | MULTIPLE_INSTANCE| Observation — wraps governance + calls  |

---

## 3. Input Alphabet for a Single Contract Call

A contract call (e.g., LLM, tool, memory) produces **7 input symbols** in the product:

```
Symbol 1:  {contract}_{op}_start          → Obs only (call announced)
Symbol 2:  governance_authorize           → Gov checks; Obs records decision
Symbol 3:  observability_pre_execute      → Obs records pre-execution state
Symbol 4:  {contract}_{op}_execute        → All machines: contract fires here
Symbol 5:  observability_post_execute     → Obs records post-execution state
Symbol 6:  governance_validate            → Gov validates result; Obs records
Symbol 7:  {contract}_{op}_end            → Obs only (call closed)
```

**Why 7, not 6?**

- Symbols 1 and 7 are pure observability bookends (span open / span close).
- Symbols 3 and 5 are observability checkpoints *between* governance and execution.
  Without them, observability cannot record the pre/post state of the contract
  call independently of governance.
- Symbol 4 is the only symbol where the capability contract (model, tool, etc.)
  actually fires.

**Governance sees**: symbols 2, 4, 6 — it can authorize, observe execution, validate.  
**Observability sees**: all 7 symbols — full trace coverage.  
**Capability contract sees**: symbol 4 only.

This is **strictly equivalent** to the former hook-plane ordering:

```
Former hook phases:          Mealy input symbol:
─────────────────────────────────────────────────
pre_llm_call  (phase ≤19)  → governance_authorize  (symbol 2)
                            → observability_pre_execute (symbol 3)
execute()                  → {contract}_execute    (symbol 4)
post_llm_call (phase ≥80)  → observability_post_execute (symbol 5)
                            → governance_validate  (symbol 6)
```

---

## 4. Full Input Alphabet (all agent events)

```python
class ContractInput(str, Enum):
    # ── Agent lifecycle ──────────────────────────────────────────────
    AGENT_START          = "agent_start"
    AGENT_END            = "agent_end"
    ITERATION_START      = "iteration_start"
    ITERATION_END        = "iteration_end"

    # ── Context assembly (ctx + cm) ──────────────────────────────────
    CTX_COLLECT_START    = "ctx_collect_start"
    CTX_COLLECT_EXECUTE  = "ctx_collect_execute"
    CTX_COLLECT_END      = "ctx_collect_end"
    CM_ASSEMBLE_START    = "cm_assemble_start"
    CM_ASSEMBLE_EXECUTE  = "cm_assemble_execute"
    CM_ASSEMBLE_END      = "cm_assemble_end"

    # ── LLM call (model) ─────────────────────────────────────────────
    LLM_START            = "llm_start"
    GOVERNANCE_AUTHORIZE = "governance_authorize"
    OBS_PRE_EXECUTE      = "observability_pre_execute"
    LLM_EXECUTE          = "llm_execute"
    OBS_POST_EXECUTE     = "observability_post_execute"
    GOVERNANCE_VALIDATE  = "governance_validate"
    LLM_END              = "llm_end"

    # ── Tool call (tool) ─────────────────────────────────────────────
    TOOL_START           = "tool_start"
    # GOVERNANCE_AUTHORIZE (reused)
    # OBS_PRE_EXECUTE      (reused)
    TOOL_EXECUTE         = "tool_execute"
    # OBS_POST_EXECUTE     (reused)
    # GOVERNANCE_VALIDATE  (reused)
    TOOL_END             = "tool_end"

    # ── Memory call (memory) ─────────────────────────────────────────
    MEMORY_START         = "memory_start"
    MEMORY_EXECUTE       = "memory_execute"
    MEMORY_END           = "memory_end"

    # ── Error / interrupt ────────────────────────────────────────────
    CONTRACT_ERROR       = "contract_error"
    INTERRUPT_SIGNAL     = "interrupt_signal"
    SHUTDOWN             = "shutdown"
```

---

## 5. The Product Step Sequence for an LLM Call

```
product.step(LLM_START)             # 1. Obs opens span; Gov notes call start
product.step(GOVERNANCE_AUTHORIZE)  # 2. Gov authorizes; Obs records decision
product.step(OBS_PRE_EXECUTE)       # 3. Obs records pre-execution snapshot
result = model.generate(messages)   # 4. Actual LLM call (not a product step)
product.step(LLM_EXECUTE)           # 4b. Product notified of execution result
product.step(OBS_POST_EXECUTE)      # 5. Obs records post-execution snapshot
product.step(GOVERNANCE_VALIDATE)   # 6. Gov validates result; Obs records
product.step(LLM_END)               # 7. Obs closes span
```

**Note on step 4**: The capability contract fires *outside* the product step.
The product is notified via `LLM_EXECUTE` with the result in `context.metadata["result"]`.
This preserves the product's purity — it never calls I/O directly.

---

## 6. Observability Wrapping Invariant

For every contract call, the observability machine must emit:

| Symbol          | Obs output          | Meaning                        |
|-----------------|---------------------|--------------------------------|
| `*_start`       | `EMIT_SPAN`         | Open OTel span                 |
| `gov_authorize` | `EMIT_EVENT`        | Record authorization decision  |
| `obs_pre`       | `EMIT_EVENT`        | Record pre-execution state     |
| `*_execute`     | `EMIT_EVENT`        | Record execution result        |
| `obs_post`      | `EMIT_EVENT`        | Record post-execution state    |
| `gov_validate`  | `EMIT_EVENT`        | Record validation decision     |
| `*_end`         | `CLOSE_SPAN`        | Close OTel span                |

This gives **4 EMIT_EVENT + 1 EMIT_SPAN + 1 CLOSE_SPAN = 6 observability outputs**
per call, regardless of which contract fires.

---

## 7. Governance Wrapping Invariant

For every contract call, the governance machine must fire at:

| Symbol          | Gov action          | Meaning                          |
|-----------------|---------------------|----------------------------------|
| `gov_authorize` | Check policy        | May raise `GovernanceError`      |
| `gov_validate`  | Validate result     | May raise `GovernanceError`      |

**Governance never fires on `*_start`, `obs_*`, `*_execute`, or `*_end`.**
This is a formal invariant: governance only touches symbols 2 and 6 of the 7-symbol sequence.

---

## 8. Context Sources in the Product

Context assembly is itself a multi-step product sequence:

```
product.step(CTX_COLLECT_START)    # Obs opens context span
product.step(CTX_COLLECT_EXECUTE)  # ContextContract machines fire
                                   # (system, memory, tools, agents, skills, ...)
product.step(CTX_COLLECT_END)      # Obs closes context span

product.step(CM_ASSEMBLE_START)    # Obs opens CM span
product.step(CM_ASSEMBLE_EXECUTE)  # ContextManagerContract trims to token budget
product.step(CM_ASSEMBLE_END)      # Obs closes CM span
```

Each `ContextContract` plugin (system identity, memory, tools, sub-agents, skills,
ontology, shared blackboard) is a sub-machine in the product. Their outputs are
`ContextPart` objects collected by the CM machine.

The CM machine (ContextManagerContract) is a SINGLE_INSTANCE machine that:
1. Receives all `ContextPart` outputs from ctx machines
2. Orders by `placement + priority`
3. Trims to token budget
4. Emits the final `messages[]` list

---

## 9. Full Agent Execution Trace (one ReAct iteration)

```
AGENT_START
ITERATION_START
  CTX_COLLECT_START
  CTX_COLLECT_EXECUTE        ← all ctx sources fire
  CTX_COLLECT_END
  CM_ASSEMBLE_START
  CM_ASSEMBLE_EXECUTE        ← CM trims to budget
  CM_ASSEMBLE_END
  LLM_START
  GOVERNANCE_AUTHORIZE       ← gov checks LLM call
  OBS_PRE_EXECUTE            ← obs snapshots pre-state
  [model.generate()]         ← actual call (outside product)
  LLM_EXECUTE                ← product notified with result
  OBS_POST_EXECUTE           ← obs snapshots post-state
  GOVERNANCE_VALIDATE        ← gov validates LLM response
  LLM_END
  [for each tool call:]
    TOOL_START
    GOVERNANCE_AUTHORIZE     ← gov checks tool call
    OBS_PRE_EXECUTE          ← obs snapshots pre-state
    [tool.execute()]         ← actual call (outside product)
    TOOL_EXECUTE             ← product notified with result
    OBS_POST_EXECUTE         ← obs snapshots post-state
    GOVERNANCE_VALIDATE      ← gov validates tool result
    TOOL_END
ITERATION_END
AGENT_END
```

---

## 10. Implementation: `execute_contract_call`

The `MealyProductIntegration.execute_contract_call()` method implements
the 7-symbol sequence for any contract call:

```python
def execute_contract_call(self, contract_type, operation, execute_fn, context):
    # 1. Obs opens span
    self.step(f"{contract_type}_start", context)
    
    # 2. Gov authorizes; Obs records decision
    self.step("governance_authorize", context)
    
    # 3. Obs records pre-execution snapshot
    self.step("observability_pre_execute", context)
    
    # 4. Actual call (outside product — preserves purity)
    result = execute_fn()
    context.metadata["result"] = result
    
    # 4b. Product notified with result
    self.step(f"{contract_type}_execute", context)
    
    # 5. Obs records post-execution snapshot
    self.step("observability_post_execute", context)
    
    # 6. Gov validates; Obs records decision
    self.step("governance_validate", context)
    
    # 7. Obs closes span
    self.step(f"{contract_type}_end", context)
    
    return result
```

**Governance denial** is detected by inspecting the output of steps 2 and 6.
If any governance machine returns `Output.ABORT_EXECUTION`, a `GovernanceError` is raised.

---

## 11. Why This Is Correct

The 7-symbol sequence is the **minimal** sequence that satisfies:

1. **Full observability**: every state transition (before/after gov, before/after call) is observable.
2. **Full governance**: gov sees the call before and after execution.
3. **Product purity**: no sub-machine calls I/O directly; all side-effects are in `execute_fn`.
4. **Formal equivalence**: isomorphic to the former hook-plane ordering (§3 above).
5. **Composability**: any number of governance/observability machines can be added without changing the sequence.
