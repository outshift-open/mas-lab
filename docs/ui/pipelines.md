<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Pipelines

A pipeline is an ordered set of steps — each with a type, optional `depends_on` dependencies,
and step-specific config — that runs against the output of a specific experiment, typically to
extract stats, evaluate metrics, or generate plots from a completed run. In the sidebar it sits
between **Experiments** and **Datasets**: Applications → Playground → Experiments →
**Pipelines** → Datasets → Overlays → Control Panel.

## Where to find it

- `/:library/pipelines` — the pipelines table
- `/:library/pipelines/new` and `/:library/pipelines/new/:pipelineTab` — create a new pipeline (`:pipelineTab` is `graph` or `yaml`)
- `/:library/pipelines/:id` and `/:library/pipelines/:id/:pipelineTab` — view/edit an existing pipeline

## What you can do here

**Pipelines table.** Lists every pipeline manifest in the library with its name, description,
attached experiment, step count, and — once you run it — a live **Status** (Inactive, Running,
Completed, Failed, Cancelled, Timeout), plus **Output**/**Errors** columns showing the job's
stdout/stderr. Clicking a row's name opens it for editing. The row action menu offers **Run**
(submits the job and polls it, showing "Running..." while in flight) and **Delete**; you can
also select multiple rows and use **Delete Selected (N)**. Either delete path opens a
"Confirm Delete" dialog before removing anything. Use **Add Pipeline** to start a new one.

**Pipeline editor.** Both the "new" and existing-pipeline pages share the same **Graph** /
**Yaml** tabs:

- **Graph** — a node-based canvas (React Flow) with an **Experiment** selector at the top and a
  step palette on the side, grouped by category (data, execution, extraction, normalization,
  analysis, evaluation, visualization, graph). Drag a step type onto the canvas to create a step
  node; each node exposes a **Name** field, a **Config** section with fields defined by that step
  type, and a read-only **Depends On** list. Drawing a connection between two step nodes' handles
  adds the source step to the target step's `depends_on`.
- **Yaml** — a read-only, generated preview of the pipeline manifest (`pipeline.yaml`) built from
  the current graph.

The existing-pipeline page additionally shows a **Run** button and an output panel (success/error
alert with stdout or stderr) once you run it directly from the editor.

!!! note
    **Save** and **Validate** are disabled until an experiment is attached in the Graph tab's
    Experiment selector — the pipeline is written against that experiment's output directory, so
    it can't be validated or saved without one.

## Task walkthrough

Build a new pipeline and run it:

1. From the Pipelines table, click **Add Pipeline**.
2. On the **Graph** tab, use the **Experiment** dropdown to attach the experiment whose run
   output this pipeline will process.
3. Drag a step type from the side panel onto the canvas to add your first step node. Set its
   **Name** and fill in any **Config** fields.
4. Add more steps one at a time the same way, then connect each step's output handle to the next
   step's input handle to wire up `depends_on` between them.
5. Switch to the **Yaml** tab at any point to review the generated manifest.
6. Click **Validate** to check the pipeline before saving.
7. Click **Save**, give it a **Pipeline Name** (and optional description) in the dialog, and
   confirm — this creates the pipeline and returns you to the Pipelines table.
8. From the table, use the row's **Run** action (or open the pipeline and click **Run**) to
   execute it. Watch the **Status**/**Output**/**Errors** columns update as the job progresses.

!!! note
    Runs are tracked as background jobs. If you navigate away or reload the Pipelines page while
    a run is in flight, the table reconnects to the job and keeps polling it, so status and
    output aren't lost.

## Related

- [Pipeline manifest](../manifests/pipeline.md)
- [Experiments](experiments.md) — a pipeline must be attached to an experiment
- [Web UI overview](index.md)
