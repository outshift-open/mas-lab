<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Lifecycle Control Lab — Results

## OSS status (mas-lab)

The main experiment [`experiment.yaml`](experiment.yaml) is **runnable** with mock or live LLM:

- Exp 2.1 — governance stacking (baseline → budget → guardrail → production)
- Exp 2.2 — SRE triage flavour conformance
- Exp 2.3 — unified governance policy model
- Pipeline figures: per-call overhead, policy density, fault detection heatmap

```bash
mas-lab benchmark run labs/lifecycle-control.lab/experiment.yaml --dry-run
```

Sub-experiment [`02-bit-exactness/`](02-bit-exactness/) reproduces topology bit-exactness with **lab-local overlays** (no cross-lab symlinks).

**Observability:** OSS overlays use the `native` plugin only. `otel_sdk` / `otel_extended` variants and KG/ontology span pipelines are in **`mas-lab-internal`** (no `otel_sdk` → `otel` normalization in OSS ctl).

Exp 2.2 (SRE triage contract conformance) is **not in OSS** — it ships in the private extensions repo.

Extended eval experiments (semantic PII judge, homoglyph robustness, paired t-tests) are **future work**.

---

## Bit-exactness (02-bit-exactness)

See historical analysis in this file's git history. The `02-bit-exactness/experiment.yaml` pipeline is fully reproducible via `mas-lab benchmark run`.
