<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Lab manifests (`mas-lab-bench`)

A **lab** is a `*.lab/` folder: `experiment.yaml`, `lab-config.yaml` (local **pipeline step**
libraries), **datasets**, and **overlays**. Validated by `mas-lab benchmark run --dry-run`.

**Terms:** [glossary.md](../glossary.md) · Demo walkthrough: [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md).

Benchmark and analysis manifests. Authoritative schemas:
`docs/schemas/lab/` (resolved at runtime via `mas.lab.schemas.paths.lab_schema_dir`).

Validated by `mas.lab.manifests.validator` and `mas-lab benchmark run --dry-run`.

---

## Manifest index

| Manifest | Schema file | Reference |
|----------|-------------|-----------|
| Experiment | `experiment.schema.yaml` | [experiment.md](experiment.md) |
| Dataset | `dataset.schema.yaml` | [dataset.md](dataset.md) |
| Post-processing pipeline | `pipeline.schema.yaml` | [pipeline.md](pipeline.md#post-processing-pipeline) |
| Pipeline library file | `pipeline-manifest.schema.json` | [pipeline.md](pipeline.md#pipeline-library-kind-pipeline) |
| Lab config | `lab-config.schema.yaml` | [user-config.md](../user-config.md) |

API ids (controller): `experiment`, `dataset`, `pipeline-post`, `pipeline`.

---

## Experiment lifecycle model

```text
experiment
├── application   pre/post  (once per experiment)
├── scenario      pre/post  (per scenario column)
├── test          pre/post  (per scenario × dataset item)
└── run           pre/post  (per run index; declares n_runs)
```

Each `pre:` / `post:` entry is a **list of pipelines** (inline steps, file `ref`, or library `{id:}`).

---

## Relationship to runtime manifests

| Lab concept | Runtime manifest |
|-------------|------------------|
| `applications[].manifest` | `kind: MAS` path |
| `scenarios[].overlays` | `kind: Overlay` stack |
| `dataset` | `kind: Dataset` |
| Benchmark flavour / infra | CLI flags + experiment YAML → resolve to Flavour / infra_refs |

## Bench-only infrastructure types

Post-run export codecs (ClickHouse, Neo4j, filesystem) use **`mas.lab.infra`**
(`DatastoreSpec`, `resolve_datastore`). These are **not** part of mas-runtime or
mas-ctl — see `lab/components/bench/src/mas/lab/infra/README.md`.

---

## Further reading

- [experiment.md](experiment.md)
- [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md)
