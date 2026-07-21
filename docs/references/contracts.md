<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Contracts

Contracts define **stable runtime boundaries** in `mas-runtime`. A contract
describes what the kernel may call (tools, models, sessions, messaging,
governance); a **plugin** implements one or more contracts.

Machine-readable registry:
[`contracts-registry.yaml`](../schemas/contracts-registry.yaml).

---

## Implemented in this release (OSS)

These boundaries are wired in the kernel and exercised by tutorials and paper labs:

| Contract / plugin | Role |
| --- | --- |
| `ToolContract` | Tool listing and invocation |
| `MemoryContract` | Memory read/write at engine boundary |
| `ContextContract` / `ContextManagerContract` | Prompt and conversation context |
| `DesignPatternPlugin` | ReAct, chain-of-thought, single-pass lifecycles |
| `EngineContract` | LLM, tool, and memory I/O |
| `CtxAssembler` | Context / prompt assembly |
| `ObservabilitySink` / `EventEmitter` | Trace and JSONL event emission |
| `BudgetTracker` + budget overlays | Stateful token/cost governance (`lifecycle-control.lab`) |

The [plugin registry](../schemas/contracts-registry.yaml) lists ingress/egress
events and Python modules for each registered contract.

---

## Taxonomy (design target)

The runtime design groups boundaries into three families. Additional contracts
below are **specified** for extension authors; not all have standalone Python
protocol classes in OSS yet.

| Family | Meaning | Examples |
| --- | --- | --- |
| **Capability** | What the runtime can access or expose | `ToolContract`, model access, `SessionContract` |
| **Orchestration** | How control flows across agents | `WorkflowContract`, delegation, transport |
| **Governance** | What is permitted | Budget, routing (sandbox/TBAC: internal-only) |

For method signatures and implementation detail on implemented contracts, see
[developer contract reference](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/index.md)
in the repository (clone required).

---

## Contract groups (developer reference)

| Group | Topics |
| --- | --- |
| Models, prompts, tools, memory | Tool and model access, prompt assembly, memory backends |
| Sessions, checkpoints, context | Session load/save, shared context, prompt context |
| Messaging & orchestration | Sensors, transport, delegation, workflow |
| Control & observability | Execution control, recorder / trace emission |
| Governance | Budget, routing (sandbox/TBAC documented in mas-lab-internal) |
| Design patterns | ReAct, chain-of-thought, single-pass lifecycles |

Deep dives (GitHub):
[model & tools](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/model-and-tools.md)
·
[state & context](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/state-and-context.md)
·
[messaging & orchestration](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/messaging-and-orchestration.md)
·
[execution control](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/execution-control-and-observability.md)
·
[governance](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/governance.md)
·
[design patterns](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/design-patterns.md)

---

## Governance (OSS)

Stateful governance plugins enforce policy across turns. The paper
**lifecycle-control** lab stacks budget caps, guardrails, and HITL via overlays
(e.g. `budget-cap` on `budget_threshold`).

Runtime implementation: `BudgetTracker` in `runtime/src/mas/runtime/boundary/gov/budget.py`.
Design-target contract: `BudgetContract` (see dev [governance.md](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/dev/contracts/governance.md)).

Egress/ingress decisions on every tool/LLM/memory call go through two layers,
evaluated in order:

1. **Declarative policies** — `GovernancePolicyEngine` (`runtime/src/mas/runtime/boundary/gov/policy_engine.py`)
   matches YAML-authored `PolicyDefinition`s (trigger condition + `action`:
   `hitl`/`block`/`terminate`/`log`/`modify`/`skip`/`retry`/`blacklist`)
   against the call, keyed off `spec.governance` in the agent/overlay manifest.
   A matched policy's own `params.message` (or `params.reason`) becomes the
   decision's reported reason; otherwise a reason is synthesized from the
   policy name and action.
2. **Parametric profiles** — `GovPolicyProfile` (egress) / `GovIngressProfile`
   (ingress) fallback when no declarative policy matches: fixed postures like
   `block-destructive`, `hitl-destructive`, `retry-on-error`. Implementation:
   `resolve_egress_governance` / `egress_governance_outcome` /
   `ingress_governance_outcome` in `runtime/src/mas/runtime/boundary/gov/policy.py`.

Every decision is emitted as a `governance_decision` observability event
(`hook`, `checkpoint`, `decision`, `reason`, `policy_name`) — this is what the
multilevel trajectory plot's Governance lane and per-call badges render (see
[pipeline-processors.md § Multilevel trajectory plot](../../lab/docs/pipeline-processors.md#multilevel-trajectory-plot)).

---

## Plugin registry (v2)

The registry maps contract IDs to Python modules and (where applicable) Mealy /
TLA machines. Registered contracts in this release:

| ID | Role |
| --- | --- |
| `DesignPatternPlugin` | Reasoning pattern scheduler (ReAct, CoT, single-pass) |
| `EngineContract` | LLM, tool, and memory I/O |
| `CtxAssembler` | Prompt / context assembly |
| `HitlResponder` | Human-in-the-loop approval |
| `ObservabilitySink` | Trace and event emission |
| `EnvelopeProduct` | Contract-call envelope (governance + observability wrap) |
| `EventEmitter` | JSONL / stderr event sinks (`mas-ctl`) |
| `EventTransform` | Boundary → native / OTEL transforms |

See [`contracts-registry.yaml`](../schemas/contracts-registry.yaml) for aliases,
ingress/egress events, and bundled implementations.

---

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

---

## Related

- [Runtime manifest fields](../manifests/runtime.md) — YAML authors
- [Schema index](schemas.md) — validation schemas
- [Mealy machines guide](https://github.com/outshift-open/mas-lab/blob/main/runtime/docs/mealy-machines-guide.md)
- [Glossary](../glossary.md) — vocabulary
- [ADR 0002](adr-0002-observability-event-model.md) — why the `ObservabilitySink` /
  `EventEmitter` boundary above records an announced stream of events rather
  than exposing a query interface
