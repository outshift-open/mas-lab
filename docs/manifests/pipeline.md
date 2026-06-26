<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Pipeline manifests

**Package:** `mas-lab-bench` · Two formats — do not mix them in one file.

A **pipeline** is an ordered list of **pipeline steps** (e.g. `extract_trace_stats`,
`plotnine`) that read **run** artifacts such as **`events.jsonl`** and write CSV/PNG under
`results/`. An **embedded pipeline** lives in `experiment.yaml`; a standalone file is run with
`mas-lab benchmark pipeline run`.

**Terms:** [glossary.md](../glossary.md) · Hands-on: [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md).

---

## Post-processing pipeline (`pipeline:` root)

**Schema:** `pipeline.schema.yaml` · **API id:** `pipeline-post`

Used by the **benchmark executor** for analysis DAGs embedded in experiments or standalone files.

```yaml
pipeline:
  name: t3-analysis
  output:
    base_dir: ./output
  steps:
    - name: extract
      type: extract_trajectories
      depends_on: []
    - name: plot
      type: plot_trajectory
      depends_on: [extract]
```

Steps reference upstream outputs via template paths (`{{run.output_dir}}/...`) in experiment
context.

---

## Pipeline library (`kind: Pipeline`)

**Schema:** `pipeline-manifest.schema.json` · **API id:** `pipeline`

Stored under `lab/pipelines/*.yaml`; edited in **mas-lab-ui** PipelineBuilder; validated by
`POST .../pipelines/validate`.

```yaml
apiVersion: mas/v1
kind: Pipeline
metadata:
  name: analysis
spec:
  steps:
    - name: extract
      type: extract_trajectories
      depends_on: []
    - name: stats
      type: extract_trace_stats
      depends_on: [extract]
      config:
        output: "{output_dir}/results/trace_stats.csv"
```

UI may emit `x-canvas-positions` (stripped before execution).

---

## Steps, types, and artifacts

- **DAG:** `depends_on` with cycle detection (controller + executor).
- **Step types:** registered processors (`extract_trajectories`, `extract_trace_stats`,
  `eval_mce`, `plot_*`, …). Full catalog: [pipeline steps](https://github.com/outshift-open/mas-lab/blob/main/lab/docs/pipeline-steps.md).
- **Artifacts:** typed values passed between steps — in-process during execution; serializable
  to files or infra sinks when a step writes `outputs` paths.

---

## See also

- [experiment.md](experiment.md)
- [lab.md](lab.md)
