<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Theoretical contribution

Formal foundation for the MAS Lab Mealy product model.

---

## Primary references (in-repo)

| Document | Content |
|----------|---------|
| [automaton-product-model.md](automaton-product-model.md) | Agent as product of Mealy machines + DP scheduler |
| [mealy-product-formal-design.md](mealy-product-formal-design.md) | Seven-symbol call envelope, σ ordering |
| [mealy-machines-guide.md](mealy-machines-guide.md) | Practitioner guide to summands |
| [dev/contracts/mealy-hooks-and-closure.md](dev/contracts/mealy-hooks-and-closure.md) | Hook ↔ symbol closure |

---

## Research article

The **MAS-Lab** article (*A Specification-Driven Validation Framework for
Reliable Multi-Agent Systems*) motivates the manifest + benchmark + trace
methodology. Reproduce Section 5 experiments via [docs/paper/index.md](../../docs/paper/index.md).

Preprint citation: see paper README for current arXiv status.

---

## Formal verification

TLA+ specifications and TLC model-checking gates are maintained **outside** this
OSS release. The Python kernel is tested with pytest (`runtime/tests/`); see
[mealy-envelope.md](mealy-envelope.md) for the implementation checklist aligned
with the formal spec.

---

## Implementation map

Do not read the 1400-line automaton doc as “all shipped.” Use:

1. [mealy-envelope.md](mealy-envelope.md) §2 — enforced features  
2. [automaton-product-model.md](automaton-product-model.md) §14 — current vs target  
3. [architectural-decisions.md](architectural-decisions.md) — ADRs
