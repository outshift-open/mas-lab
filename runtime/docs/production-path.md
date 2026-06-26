<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Production execution path

The supported way to run agents in production is the **kernel envelope path**:

```
RuntimeInstance → KernelDriver → RuntimeKernel (envelope contracts)
```

Legacy alternatives (`BaseAgent`, `HookRegistry`, skeleton hook-plane) have been removed; use the kernel envelope path only.

## Components

| Layer | Module | Role |
|-------|--------|------|
| Embed API | `mas.runtime.driver.instance.RuntimeInstance` | Session surface: `run_user_text`, pause/resume/abort, snapshots |
| Driver loop | `mas.runtime.driver.driver.KernelDriver` | Closes the Mealy loop: feeds Σ_in, auto-dispatches Σ_out to engine, HITL, and context |
| Kernel | `mas.runtime.kernel.orchestrator.RuntimeKernel` | Pure transition function: ingress symbol → egress symbol list |
| Envelope | `mas.runtime.kernel.envelope` | Governance, observability, and contract execution on every crossing |

## Data flow

1. **Ingress** — `UserInputReceived`, `EngineIoReturn`, `HitlResolve`, or lifecycle symbols enter via `RuntimeInstance.feed()` / `KernelDriver.feed()`.
2. **Kernel transition** — `RuntimeKernel.transition()` updates `QProduct` state and emits egress symbols (`InvokeEngineIo`, `EmitHitlRequest`, `RequestCtxAssembly`, etc.).
3. **Driver dispatch** — `KernelDriver` executes side effects (LLM/tool engine, HITL responder, context assembly) and feeds results back as ingress.
4. **Envelope** — Each engine crossing runs through `EnvelopeContext` and `run_contract_execute_obs` / `run_ingress_validate_envelope` before commit.

## Building a runtime

```python
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.engine.simulated import SimulatedEngine

instance = RuntimeInstance.from_parts(engine=SimulatedEngine())
trace = instance.run_user_text("Hello")
```

For configured agents, use `RuntimeBuilder` (`mas.runtime.factory.builder`) to wire manifest, engine, and HITL adapters into a `RuntimeInstance`.

## What is not the production path

- **`HookRegistry` / `BaseAgent` / `skeleton/`** — removed; do not reintroduce a parallel hook-plane.
- **`topology/`** — removed; workflow routing belongs in design-pattern plugins and manifest delegation config.
- **`boundary/grpc/` stub** — placeholder only; no production transport until Phase 4D protobuf stubs land.

## Related docs

- [Mealy envelope](mealy-envelope.md)
- [Automaton product model](automaton-product-model.md)
- [Design patterns](design-patterns.md)
