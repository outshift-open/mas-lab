<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# ADR 0001 — "lab", "labs", and "components" terminology

**Status:** Accepted (terminology) · Rename of `mas.lab.components` **deferred** (see below)
**Date:** 2026-06-29

## Context

The word *lab* and the word *components* are each overloaded in this repository,
which makes the tree hard to navigate for newcomers. Concretely:

| Name | What it actually is |
| --- | --- |
| `lab/` | The `mas-lab` umbrella **package** (the published meta-package; CLI entry `mas.lab.cli:app`). |
| `lab/components/{core,bench,controller,content}/` | Four separately-published **wheels** (`mas-lab-core`, `mas-lab-bench`, …). The tutorial runner (`mas-lab-tutorial`) is internal-only in `mas-lab-internal`. |
| `labs/` | The three paper **lab definitions** (`design-space.lab`, `extensions.lab`, `lifecycle-control.lab`) plus `labs/results/`. These are data/config, not code. |
| `library-lab/` | `mas-library-lab` — a thin facade package exposing public eval plugins (delegates to `mas-library-eval`). |
| `mas.lab.components` (i.e. `lab/src/mas/lab/components/`) | A **runtime module directory** (llm, mitm, executor, ui, metrics, observability, …). Unrelated to the build "components" above. |

So *components* means both "the published sub-wheels" and "an internal runtime
module package", and *lab* spans a package, a directory of data, and a facade
library. Nothing here is functionally broken — Python namespaces keep
`lab/components/*/src/mas/lab/...` (which installs into the `mas.lab` namespace)
distinct from the `mas.lab.components` subpackage — but the naming is a
readability hazard.

## Decision

1. **Canonical vocabulary** (use these terms consistently in docs and code):
   - **package** — a published wheel (`mas-lab`, `mas-lab-core`, …).
   - **component** — one of the five sub-wheels under `lab/components/`.
   - **lab (definition)** — a `*.lab` folder under `labs/` describing a paper experiment.
   - **runtime modules** — the internal code under `mas.lab.*` that components ship.
2. Document this table in the glossary and the packages reference.
3. **Rename `mas.lab.components` → `mas.lab.runtime_modules`** to remove the
   collision with the `lab/components/` wheels — see the recipe below. This step
   is **deferred** until it can be validated against the full test suite, because
   it touches *dynamic* references that static analysis cannot verify.

## Why the module rename is deferred (not done in this pass)

`mas.lab.components` is referenced not only by ordinary `import` statements but by
**dynamic string imports** that only fail at runtime:

- `lab/src/mas/lab/components/controller/backends.py:52-53` —
  `"mas.lab.components.metrics.server:main"`, `"mas.lab.components.llm.mock_server:main"`
  (spawned via `python -m …`).
- `lab/components/bench/src/mas/lab/benchmark/pipeline/steps/eval/annotate_metrics.py:173` —
  `_DEFAULT_METRIC_CLASS = "mas.lab.components.evaluation.deepeval_wrapper.AnswerRelevancyMetric"`.
- `lab/components/controller/src/mas/lab/controller/routes/health.py:124` — the same
  class path as a display-name map key.
- `library-standard/src/mas/library/standard/infra/mock-llm.yaml:10` — a `python -m …` comment.

A `py_compile` pass and most unit tests will not catch a missed string here; the
metrics/llm_mock backends would simply fail when the controller spawns them. The
rename should therefore land in a change set where `pytest` (and a backend-spawn
smoke test) can confirm it.

## Rename recipe (for the test-gated follow-up)

1. `git mv lab/src/mas/lab/components lab/src/mas/lab/runtime_modules`.
2. Replace every dotted occurrence of `mas.lab.components` with
   `mas.lab.runtime_modules` (imports **and** strings). Exhaustive current list:
   - `lab/src/mas/lab/runtime_modules/observability/otlp_http_local.py`
   - `lab/src/mas/lab/runtime_modules/controller/backends.py` (×2 strings)
   - `lab/src/mas/lab/runtime_modules/common/telemetry_feed.py`
   - `lab/src/mas/lab/runtime_modules/evaluation/interface.py` (docstring)
   - `lab/components/bench/src/mas/lab/benchmark/pipeline/steps/eval/annotate_metrics.py`
   - `lab/components/controller/src/mas/lab/controller/routes/health.py`
   - `library-standard/src/mas/library/standard/infra/mock-llm.yaml`
3. Grep-verify zero remaining `mas\.lab\.components` references.
4. Run the full suite **and** start the controller so the `metrics` and `llm_mock`
   backends spawn (covers the dynamic imports).
