<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Overview

MAS-Lab is for **developers**, **enterprises**, and **researchers** who need
multi-agent systems that remain understandable as they grow. This page expands on
[the home introduction](index.md) for each audience.

[Back to home](index.md)

---

## For developers

Build modular multi-agent applications using explicit specifications instead of
hidden prompt and code glue.

Declare agents, tools, workflows, and contracts once, then iterate safely across
models, tools, and coordination patterns. The runtime enforces contracts at
important boundaries — tool calls, delegations, model requests — so changes do
not propagate unpredictably through the whole stack.

Use the [design-space labs](paper/index.md) to compare coordination patterns and
topologies before production. Start with [Tutorial 0](tutorials/00-environment-setup/README.md).

---

## For enterprises

Deploy agentic systems with governance, traceability, and operational control
built in.

MAS-Lab separates business intent, runtime execution, observability, and policy
enforcement. Governance policies — budgets, approvals, delegation rules, tool
access — are expressed as overlays rather than buried in application code.

See the [user guide](user-guide.md) for install, configuration, and day-to-day
workflows.

---

## For researchers

Run controlled, reproducible experiments on multi-agent systems.

Experiments tie to an explicit specification, so observed differences are more
likely to reflect the variable you changed — not hidden stack drift. Multi-run
campaigns, overlays, and integrated observability support rigorous comparison of
agent designs, coordination patterns, and governance mechanisms.

Reproduce the article's Section 5 evaluations via [paper labs](paper/index.md).

---

## The problem in brief

Prototype multi-agent demos are easy; production-grade trust is not. When logic,
orchestration, and control are interwoven, teams struggle to reproduce behavior,
attribute failures, or evolve systems safely.

MAS-Lab's response is a **specification-driven foundation**: intent, execution,
observability, experimentation, and governance share one model — from the first
lab run through deployment. See [the home page](index.md) for a short introduction.
