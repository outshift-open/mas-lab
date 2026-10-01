<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Thin waist — one registry per conceptual job

The runtime waist is **name → implementation** through either
`PluginRegistry` (manifest-facing, agent-selectable behaviour) or
`component-registry.yaml` (embedder-chosen infra: runtime / placement /
framework). A third dict or enum that maps the same names is a duplicate
kernel.

This note is the audit method from PLAN-07 §3, plus the 2026-10-02 sweep
on `feature/plan-07-consolidation`. PLAN-08/09/10 extension points must
land as a registry category from the first commit.

## Detector

Grep `runtime/`, `ctl/`, and `library-*` for:

1. `Enum` classes whose values are manifest-facing strings (`spec.*`,
   `kind:`, `type:`, plugin ids).
2. Module-level `dict` / `frozenset` literals whose keys are the same
   class of names.

Then classify each hit:

| Hit | Action |
| --- | --- |
| A `PluginRegistry` category already exists | Close the parallel table (the `SkillPluginRegistry` case). |
| No category yet, and ≥1 real consumer | Candidate new category — only after PLAN-00 anti-pattern #4 (one real consumer before designing the interface). |
| Schema / Mealy / observability vocabulary | Keep as types. These are not dispatch tables. |
| Cache populated *from* the catalog | Keep, with a comment that the catalog is authoritative. |

## Closed in this branch

`SkillPluginRegistry` no longer owns `SkillImplementation` /
`_IMPLEMENTATIONS` / `_CLASS_NAMES`. Construction goes through
`PluginRegistry.resolve_by_type("skill_impl", name)`. A fourth
`skill_impl` is a `library.yaml` row.

## Sweep findings (2026-10-02)

**Not violations** (typed state / event vocabulary, not plugin dispatch):

- Kernel Mealy: `LifecycleState`, `DpState`, `ModelState`, `ToolState`,
  `CtxState`, `MemoryState`, `SessionState`, `TransportState`, `GovState`
- Envelope / obs / HITL / ingress / egress / governance action enums
- `SessionStatus`, `ControlPhase`, `GovDecision`, `ErrorRecoveryAction`
- Lab: `OutputFormat`, `StepType`, `JobStatus`
- `OperatorMode` (operator console UX, not a plugin category)

**Catalog caches, not parallel registries:**

- `ctl/.../framework_registry.py` `_ADAPTERS`
- `ctl/.../placement_registry.py` `_BACKENDS`

Both start empty and are filled from `component-registry.yaml`. Planned
ids fail through `validate_component_id` / `get_framework_adapter`, not a
second name list.

**Left open (product, not a second registry):**

- Docker / kubernetes placement stay `status: planned` until the
  `mas.library.next` availability decision (PLAN-07 §2.6). Do not invent
  a third unlock table.

**PLAN-08 / PLAN-09 / PLAN-10:** control verbs, snapshot storage, and
live-spec delta kinds are new categories or compositions of existing
ones. Do not add `DetectiveMode` or `CheckpointPluginKind` enums.

## Completeness

The detector is necessary for *duplicate dispatch*. It is not the kernel
completeness argument — that lives in the next-release PLAN-10 (kernel
primitives): a small orthogonal catalog that is necessary and sufficient
to compose subagents, checkpoint trees, debug, and evolutionary search
on three surfaces (plugin SDK, LLM tool calling, admin control).
