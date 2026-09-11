<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->

# Tutorial 4 — The Web UI, end to end

> **Packages:** `mas-lab` (controller + UI), `mas-runtime`
> **Time:** ~60 min hands-on
> **Prerequisite:** [Tutorial 0](../00-environment-setup/) (install, PATH, model
> endpoint, API key). Tutorials 1–3 are helpful background but **not required** —
> this tutorial uses the trip-planner sample app that ships with
> `mas-library-samples`, not the one you hand-authored in Tutorial 2.

---

## Overview

Tutorials 1–3 built and ran a trip-planner MAS from the command line, one YAML
file at a time. This tutorial does the equivalent work **entirely in the
browser**, using the same Arborian Network trip-planner scenario — but starting
from the canonical sample app that `mas-library-samples` ships out of the box,
so there's nothing to author from scratch before you begin.

You'll touch all seven sections of the UI, in the order the work actually
depends on (not the sidebar order):

1. **Applications** — open and run the bundled trip-planner MAS
2. **Playground** — build a small new agent from scratch, reusing its tools
3. **Overlays** — patch one trip-planner agent's reasoning pattern
4. **Datasets** — create a small benchmark dataset
5. **Experiments** — run the base MAS with your overlay applied against that dataset
6. **Pipelines** — extract and plot the run's trajectories
7. **Control Panel** — confirm what infra config actually backed the run

Each section's UI reference page ([Applications](../../ui/applications.md),
[Playground](../../ui/playground.md), [Overlays](../../ui/overlays.md),
[Datasets](../../ui/datasets.md), [Experiments](../../ui/experiments.md),
[Pipelines](../../ui/pipelines.md), [Control Panel](../../ui/control-panel.md))
has the full field-by-field detail — this tutorial is the guided walk-through
that strings them together.

---

## Setup

Start the controller and UI (see [Tutorial 0](../00-environment-setup/) if
you haven't installed yet):

```bash
# Terminal 1 — controller
MAS_CONTROLLER_IDLE_SEC=3600 mas-lab serve

# Terminal 2 — UI
cd ui
yarn install
export VITE_API_BASE_URL=http://localhost:8090
yarn dev
```

Open the URL Vite prints (typically <http://localhost:5173>).

The library switcher is in the top-right corner. Click it and select
**Library Samples** — this is the library backed by the `mas-library-samples`
package, and it's where the bundled `trip-planner` and `qa-mas` sample apps
live.

---

## Part 1 — Applications: open and run the trip-planner MAS

1. Click **Applications** in the sidebar. The table lists two apps: `qa-mas`
   and **`trip-planner`** (tagged with 4 agents — `moderator` plus 3 more).
2. Click the `trip-planner` row to open it. The **Graph** tab loads a
   four-agent layout: **moderator** (ReAct, delegates to the other three),
   **schedule_agent** (schedules and attractions), **itinerary_agent** (route
   planning), and **concierge_agent** (fares and pricing) — the same cast as
   Tutorial 2's hand-built version, pre-wired with Model and Tools nodes.
3. Click **Validate MAS** to confirm the manifest is sound.
4. Click **Run MAS**. The moderator agent ships with a default query already
   wired into its Text Input node ("What trains run from Celestia to
   Verdantia?"), so Run MAS uses that as-is. Wait for the button to stop
   reading "Running MAS..." — the answer (or an error) appears in the Run Output tab.
5. Switch to the **Yaml** tab to see the generated `mas.yaml` and each agent's
   manifest side by side with what you just ran.

---

## Part 2 — Playground: build a small agent from scratch

Rather than rebuilding all four trip-planner agents, build one small
standalone agent that reuses the same tool catalog — this is the fastest way
to feel the canvas mechanics without repeating Tutorial 2's whole build.

1. Go to **Playground**. You land on an empty **Graph** tab.
2. Drag an **Agent** node onto the canvas.
3. Drag a **Model** node onto the canvas, then draw a connection from it to
   the Agent node's `model` handle. Pick **`azure/gpt-4o-mini`** from the
   Model dropdown.
4. Drag a **Design Pattern** node, connect it to the Agent's `design_pattern`
   handle, set **Pattern Type** to **ReAct**, and leave **Max Steps** at its
   default.
5. Drag a **Tools** node, connect it to the Agent's `tools` handle, and use
   its **"Add from list"** dropdown to add **`global/get_fares`** and
   **`global/get_attractions`** — the same tool manifests the bundled
   `concierge_agent` and `schedule_agent` use, surfaced here because they're
   registered at the library's global namespace.
6. Drag a **Text Input** node, connect it to the Agent's `text_input` handle,
   and set its System Prompt to something like _"What are the main
   attractions in Celestia and how much does the train there cost?"_
7. Open the Agent node and fill in a **Name** (`concierge-lite`), short
   **Description**, and **Instructions** (e.g. "Answer trip questions about a
   single city using the fare and attraction tools you have access to.").
8. Click **Validate** (with the agent node selected), then **Validate MAS**.
9. Click **Save**, enter **MAS Name** `concierge-lite`, an optional
   **Description**, and confirm. This creates a brand-new Application — check
   **Applications** and you'll see it listed alongside `trip-planner`.

!!! note
Playground has no **Run MAS** button. To actually run `concierge-lite`,
open it from **Applications** afterward.

---

## Part 3 — Overlays: patch the concierge agent's reasoning pattern

Now patch the _real_ trip-planner MAS instead of the one you just built —
without touching its saved manifest.

1. Go to **Overlays** and click **New Overlay**.
2. Set the **Namespace** dropdown to **`trip-planner`** — this scopes the
   overlay to that app's agents (it also lists `qa-mas` and `Global`).
3. Drag an **Agent** node onto the canvas and set it to **`concierge_agent`**.
4. Drag a **Design Pattern** node, connect it to the Agent node, and set
   **Pattern Type** to **Chain of Thought** (`cot`) with **Max Steps** around
   `6`. This is the same kind of patch as the library's pre-built
   `overlays/cot-moderator.yaml` — just targeting the concierge instead of the
   moderator.
5. Switch to the **YAML** tab to confirm the generated overlay only contains
   a patch for `concierge_agent`'s `design_pattern` — nothing else changes.
6. Click **Validate**, then **Save**. Name it `concierge-cot` with
   description "Concierge agent using Chain-of-Thought instead of ReAct",
   and confirm.

---

## Part 4 — Datasets: create a small benchmark

1. Go to **Datasets** and click **Add Dataset**.
2. Click **Add Item** and fill in:
   - **Prompt**: `What trains run from Celestia to Verdantia?`
   - **Ground Truth**: leave blank, or add a short expected answer if you want
     one for reference
3. Click **Add Item** twice more for:
   - `What are the main attractions in Celestia?`
   - `How much does a flight from Celestia to Luminos cost?`
     (These mirror three of the queries in the bundled
     `trip-planner/queries.yaml` dataset — feel free to open that dataset first
     for more examples.)
4. Click **Save**, and in the dialog give it the **Name**
   `trip-planner/tutorial-queries` (matching the folder the other
   trip-planner datasets live in) plus an optional **Description**, then
   confirm.

---

## Part 5 — Experiments: run the trip-planner MAS with your overlay

1. Go to **Experiments** and click **Add Experiment**.
2. Under **Basic Info**, set **Name** to `trip-planner-cot-check`.
3. Under **Scenarios**, check **Use Patch Overlays** — this reveals an
   **Overlay** column per scenario plus a **MAS Configuration** section below.
4. Under **MAS Configuration**, set **Base MAS Application** to
   **`trip-planner`**.
5. Fill in the scenario row: **ID** `concierge-cot`, **Overlay** set to the
   `concierge-cot` overlay you saved in Part 3, **Description** "Concierge
   agent patched to Chain-of-Thought".
6. Under **Dataset**, set **Dataset Path** to the
   `trip-planner/tutorial-queries` dataset from Part 4.
7. Under **Execution**, leave **Number of Runs** at 1 for a quick pass.
8. Under **Emulation**, pick **Infra LLM**: `live` if you have a model API key
   configured (see Tutorial 0), or `mock`/`replay` for an offline dry run.
9. Click **Save**, then open the new row's action menu and click **Run**.
   Watch the **Status** column move from Running to Completed (or Failed).
10. Once it's Completed, click the row to open the results browser and use
    the **Files** tree to inspect the run's output.

---

## Part 6 — Pipelines: extract and plot the run

1. Go to **Pipelines** and click **Add Pipeline**.
2. On the **Graph** tab, use the **Experiment** dropdown to attach
   `trip-planner-cot-check`.
3. Drag in the Extract Trajectories step from the **extraction** category that extracts run
   trajectories, and name it `extract`.
4. Drag in the Plot Multilevel Trajectories step from the **visualization** category that plots a
   trajectory, name it `plot`, and connect `extract → plot` so `plot`'s
   `depends_on` includes `extract`.
5. Switch to the **Yaml** tab to review the generated `pipeline.yaml`.
6. Click **Validate**, then **Save** with a **Pipeline Name** like
   `trip-planner-cot-analysis`.
7. From the Pipelines table, click **Run** on the new row and watch
   **Status**/**Output**/**Errors** update.
8. After the pipeline completed successfully, open the **trip-planner-cot-check** experiment page.
   There the extracted trajectories can be inspected inside the trajectories.jsonl file, and the trajectory plot through multilevel_trajectory.html

!!! note
The exact step names available in the palette depend on which pipeline
step plugins your install has registered — if steps above cannot be found,
look for the extraction and visualization category
steps closest to "extract trajectories" and "plot trajectory".

---

## Part 7 — Control Panel: confirm what backed the run

1. Go to **Control Panel**.
2. Select the **Infra** tab and pick the infra config file listed (e.g. the
   library's tool-provider/LLM routing config) to confirm which model
   provider and tool endpoints your run actually used.
3. Check the **Runtime runners** line at the top of the page for the runners
   the controller currently exposes.
4. Switch to **Workspace** to see the other files backing this library, if
   you want to cross-reference anything you changed.

Nothing here is editable — it's the read-only "why did my run do that"
answer key for everything you built in Parts 1–6.

---

## What's next

- Compare `concierge-cot` against the concierge's default ReAct behavior: add
  a second overlay that pins **Pattern Type** back to **ReAct** (the
  Experiments UI requires every patch-overlay scenario to reference an
  overlay, so this stands in for an unpatched "baseline"), add it as a second
  scenario in the same experiment, then add an evaluation step (e.g. an
  answer-relevancy metric) to your pipeline — see
  [Tutorial 3](../03-experiments-and-analysis/) for the CLI-side equivalent
  (`AnswerRelevancyMetric`, MCEv1).
- Try patching a different agent or design pattern combination, or add a
  `Tools (Remove)` node to an overlay to see how it changes the concierge's
  behavior.
- Extend `concierge-lite` from Part 2 into a small MAS of its own: drag in a
  second **Agent** node, then draw a connection from `concierge-lite`'s
  output handle (right side) to the new agent's **Text Input** handle (left
  side). That turns it into a delegation edge — the same mechanism wiring the
  trip-planner's moderator to its three specialists in Part 1 — so
  `concierge-lite` can now hand off tasks to the new agent instead of
  handling everything itself.
