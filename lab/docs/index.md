<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-lab documentation

Docs for **benchmarks**, **pipelines**, and validation.

**Start:** [labs-quickstart.md](labs-quickstart.md) · **Terms:**
[glossary.md](../../docs/glossary.md) · **Site docs:** [docs/index.md](../../docs/index.md).

## Guides

| Page | Contents |
|------|----------|
| [labs-quickstart.md](labs-quickstart.md) | Run a **lab**; **embedded pipeline** figures |
| [labs-going-further.md](labs-going-further.md) | Custom **pipeline steps**, **scenarios** |
| [benchmark.md](benchmark.md) | `mas-lab benchmark` |
| [pipeline.md](pipeline.md) | **Pipeline** YAML |
| [pipeline-steps.md](pipeline-steps.md) | Built-in step types |
| [pipeline-processors.md](pipeline-processors.md) | Processors for `type: processor` |
| [designing-experiments.md](designing-experiments.md) | **Scenario** matrices |
| [multi-scenario-format.md](multi-scenario-format.md) | **Scenarios** × **dataset** × **runs** |
| [benchmark-state-architecture.md](benchmark-state-architecture.md) | **Trace cache**, locks |
| [user-guide.md](user-guide.md) | Package overview |

## Cross-cutting

| Topic | Page |
|-------|------|
| **`events.jsonl`**, **observability** flags | [cli/observability.md](../../docs/cli/observability.md) |
| Paper **experiments** | [paper/index.md](../../docs/paper/index.md) |
| Evaluation metrics | [library-eval/README.md](../../library-eval/README.md) |

## Internals

| Page | Contents |
|------|----------|
| [PIPELINE_DESIGN.md](../components/bench/PIPELINE_DESIGN.md) | Pipeline executor |
| [bench README](../components/bench/README.md) | Full benchmark CLI |
