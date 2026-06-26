<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Architectural decisions (ADRs)

Recorded decisions for the MAS Lab runtime and tooling. Status reflects the
**v0.1 OSS** tree (`main`).

---

## ADR-1: Kernel-only production path

**Status:** Accepted  
**Context:** Legacy hook-plane and `runtime.py` monolith duplicated governance.  
**Decision:** Production execution is `RuntimeInstance → KernelDriver → RuntimeKernel`
only. Legacy paths removed.  
**Consequences:** All new features must land in kernel/envelope/driver modules.
See [production-path.md](production-path.md).

---

## ADR-2: Seven-symbol egress/ingress envelope

**Status:** Accepted (implemented)  
**Context:** Ad-hoc pre/post hooks were hard to compose and test.  
**Decision:** Every `LLM_CALL` and `TOOL_CALL` walks authorize → pre → execute →
post → validate symbols; `GuardedProductComposer` steps obs ⊗ gov ⊗ capability
summands.  
**Consequences:** Policy evaluation is centralized in `envelope.py`; Mealy
machines record state/telemetry. Checklist: [mealy-envelope.md](mealy-envelope.md).

---

## ADR-3: Design patterns as plugins, not kernel branches

**Status:** Accepted  
**Context:** ReAct-shaped loops were embedded in the old runtime.  
**Decision:** DPs implement `handle_event` / `evaluate_next` and schedule egress
symbols; kernel does not branch on pattern name.  
**Consequences:** New patterns ship as registry plugins (`plugin_registry.yaml`).

---

## ADR-4: `mas-ctl` for interactive UI, `mas-runtime` headless

**Status:** Accepted  
**Context:** Docker workers and CI should not depend on TUI code.  
**Decision:** `mas-ctl chat` / `tui` on host; `mas-runtime run-agent` for batch.
Both use `SessionController` / `instantiate_runtime`.  
**Consequences:** Runtime CLI doc points interactive users to ctl.

---

## ADR-5: `mas-lab` owns benchmarks

**Status:** Accepted  
**Context:** Benchmark orchestration was incorrectly documented on `mas-ctl`.  
**Decision:** `mas-lab benchmark run` is the only supported bench entry CLI.
Ctl provides library primitives only.  
**Consequences:** README and tutorials reference `mas-lab`, not `mas-ctl bench`.

---

## ADR-6: Declarative experiments and content-addressed traces

**Status:** Accepted  
**Context:** Paper reproduction required ad-hoc scripts per figure.  
**Decision:** `experiment.yaml` drives pipeline steps; LLM traces cached by content
hash under `MAS_TRACE_CACHE`.  
**Consequences:** Golden tests in `tests/test_golden_labs_run.py`; labs must
declare pipeline steps, not shell scripts.

---

## ADR-7: Formal specs outside OSS CI

**Status:** Accepted  
**Context:** TLA+ proofs and TLC gates are maintained separately.  
**Decision:** OSS ships Python kernel + pytest; formal proofs are companion
artifacts referenced in [mealy-product-formal-design.md](mealy-product-formal-design.md).  
**Consequences:** Normative markdown describes intent; [mealy-envelope.md](mealy-envelope.md)
§2 is the enforced implementation matrix.

---

## ADR-8: Workspace and infra separation

**Status:** Accepted (v0.1+)  
**Context:** Team proxies and secrets were conflated in manifests.  
**Decision:** `mas-workspace.yaml` + `MAS_INFRA_REFS` declare infra bundles;
secrets stay in env / `~/.mas`. Schema: `docs/schemas/mas-workspace.schema.yaml`.  
**Consequences:** `engine_factory.py` resolves model endpoint from workspace chain.

---

## Future / not in v0.1

| Topic | Notes |
|-------|-------|
| `ProductMealyComposer` offline ⊗ | Design target for model checking; runtime uses fixed triple composer |
| gRPC production transport | `boundary/grpc/` stub only |
| Full ⊗ⁿ governance family | Policy engine covers most cases; not separate Mealy per policy |

See [automaton-product-model.md](automaton-product-model.md) §14 for current vs
target map.
