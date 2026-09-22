<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Experiments

An experiment is a benchmark run configuration — an
[Experiment manifest](../manifests/experiment.md) — that binds a
[Dataset](../manifests/dataset.md) to one or more target applications/MAS and a set of
scenarios, then runs them under a chosen execution and emulation strategy. This page has two
tabs, **Experiments** (manage and run experiment configs) and **Benchmark Utilities** (analyze
or import a completed run by ID), plus a read-only results browser for any run that has
finished. In the sidebar it sits between Playground and Pipelines: Applications → Playground →
**Experiments** → Pipelines → Datasets → Overlays → Control Panel. It is the visual equivalent
of running `mas-lab benchmark run experiment.yaml` from the CLI.

## Where to find it

- `/:library/experiments` — the Experiments page (Experiments / Benchmark Utilities tabs)
- `/:library/experiments/:id` — read-only results browser for one experiment's run output

## What you can do here

### Experiments tab

A table of every experiment manifest in the library (Name, Status, Output, Errors, Description,
Version, Scenarios, Dataset — Description/Version are hidden by default). The row action menu,
opened per row, offers:

- **Run** — submits the experiment as a background benchmark job and starts polling it; the
  menu item reads "Running..." while a job is in flight for that row
- **Export** — downloads the experiment's benchmark export
- **Edit** — reopens the **Add Experiment** dialog pre-filled with this experiment's config
- **Delete Cache** — clears any cached run artifacts for the experiment
- **Delete** — asks for confirmation, then removes the experiment; you can also select multiple
  rows and use **Delete Selected (N)**

Clicking anywhere else on a row navigates to its [results browser](#experiment-results-experiment-page).
While a job runs, the **Status** column cycles through Inactive → Running → Completed/Failed/
Cancelled/Timeout, and the **Output**/**Errors** columns show a live, truncated tooltip of the
job's stdout/stderr. Use **Add Experiment** in the page header to create a new one.

### Benchmark Utilities tab

A small utility panel with a single **Benchmark id** field (accepts a short id, full id,
experiment name, `last`, or `latest`) and two actions:

- **Analyze** — submits an analyze job for that run and polls it, then shows a cleaned-up
  summary of its stdout (headers and separators stripped) in a terminal-style output panel
- **Import** — opens a file picker (`.tar.gz`, `.tgz`, `.gz`, or a plain tarball) to upload and
  import an externally-produced benchmark archive; the panel shows the uploaded file name and
  the job's resulting status once it completes

Both actions report their progress as a single status line ("submitting…", "running…", then the
final result or error) rather than a raw stdout/stderr dump.

### Experiment results (Experiment page)

Opening an experiment from the table (or navigating to `/:library/experiments/:id`) shows a
two-panel, read-only browser over that run's output directory: a **Files** tree on the left and
a content viewer on the right. Selecting a file renders it appropriately for its type —
syntax-highlighted code/YAML/JSON/CSV/Markdown/plaintext, a sandboxed HTML preview (`iframe`),
an SVG preview, or an inline image — falling back to plain code view for anything else. If the
experiment hasn't been run yet (no output directory), the page shows "Experiment not found or
not yet executed" with a button back to the Experiments table.

!!! note
    This page only reads existing run output — there's nothing here to edit or re-run. Use the
    Experiments tab's **Run** action to produce (or re-produce) results first.

## Task walkthrough

Create and run an experiment, then inspect its results:

1. From the **Experiments** tab, click **Add Experiment**.
2. Under **Basic Info**, fill in **Name** (required) and an optional **Description**.
3. Under **Scenarios**, pick a scenario **ID** from the dropdown (or, with **Use Patch Overlays**
   checked, type a custom scenario ID and attach an **Overlay**), plus optional **Description**
   and **Tags**. Use the `+` icon to add more scenarios.
4. If **Use Patch Overlays** is checked, also choose a **Base MAS Application** under
   **MAS Configuration**.
5. Under **Dataset**, choose a **Dataset Path** from the available dataset manifests.
6. Under **Execution**, set **Number of Runs**, **Parallel Scenarios**, **Timeout (s)**,
   **Pause Between Runs (s)**, and a **Strategy** (`coverage`, `random`, or `sequential`).
7. Under **Emulation**, choose **Infra LLM** (`live`/`mock`/`replay`), **Infra Tools**
   (`live`/`mock`/`stub`), and **Runtime Cache** (`content-addressed`/`disabled`/`forced`).
   Switch to the **YAML** tab at any point to review the generated manifest.
8. Click **Save** — this creates the experiment and returns you to the Experiments table.
9. Open the new row's action menu and click **Run**. Watch the **Status**/**Output**/**Errors**
   columns update as the job progresses.
10. Once the status reads Completed, click the row to open its results browser, then click
    through the **Files** tree to inspect individual outputs.

!!! note
    Runs are tracked as background jobs keyed by library + experiment name. If you reload the
    Experiments page while a run is still pending or running, it re-fetches the job list and
    resumes polling automatically, so in-flight status isn't lost.

## Related

- [Experiment manifest](../manifests/experiment.md)
- [Dataset manifest](../manifests/dataset.md)
- [Datasets](datasets.md)
- [Pipelines](pipelines.md) — a pipeline attaches to an experiment's output
- [Web UI overview](index.md)
