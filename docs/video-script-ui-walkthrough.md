<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->

# MAS-Lab Web Studio — Video Walkthrough Script

**Audience:** developers evaluating MAS-Lab for the first time
**Target length:** ~8 minutes (min. 5:00) · **Tone:** balanced, promotional-but-technical
**Format:** screen recording with voiceover · UI at `http://localhost:8080` (Docker) or `:5173` (dev)

**Key messages to land**

1. You _build_ a multi-agent system visually — agents, models, tools, skills — and it **serializes to schema-valid YAML manifests for you**. No hand-writing long manifests or memorizing field structure.
2. **Overlays** let you patch an existing MAS non-destructively — here, swapping the moderator's design pattern — so you can compare variants without forking the system.
3. You get **first-class visualization of run outputs** — traces, metrics, plots, and analysis reports.

**What we build vs. what's pre-made**

- **Built live on camera (Scene 2):** a _simple QA MAS with a single agent_ — fast, shows the authoring loop end to end.
- **Pre-created (too big to build on camera):** the **Trip Planner** MAS — a `moderator` orchestrating three specialists (`schedule_agent`, `itinerary_agent`, `concierge_agent`). This is the **base MAS for the experiment**.
- **Pre-created overlays:** `react-moderator`, `cot-moderator`, `reflection-moderator` — each patches only `agents.moderator.design_pattern`. We create one live to explain the idea, then use these.
- **Pre-created pipeline:** `pipeline-test` — a seven-step analysis pipeline (trajectories, trace stats, multilevel plot, MCE eval, metric collection, confidence intervals, comparison plot). Too involved to build on camera, so we open it and explain each step.

**The experiment's goal (state it plainly on camera):** apply three overlays over the already-built Trip Planner to swap the **moderator's design pattern** — **ReAct**, **Chain-of-Thought**, and **Reflection** — and compare how each performs on the same dataset.

**Full flow (order matters — it is a dependency chain):**
Build QA MAS → Save → Run → meet pre-built Trip Planner → review the moderator overlays → build Experiment (Trip Planner + 3 overlay scenarios) → **run Experiment (produces the execution traces)** → open the pre-built Pipeline **`pipeline-test`** and walk its steps → **run the Pipeline (produces metrics, plots, analysis)** → open the Experiment output page, where **both** the traces **and** the pipeline's assets are exported together.

---

## How to read this script

Each build-heavy scene is broken into **beats**. Every beat pairs one action with the exact line to say _while doing it_, so narration never drifts from the screen:

> **DO** — the single on-screen action
> **SAY** — the line to speak _during_ that action (written for ~140 wpm; a beat is ~4–8 seconds)

Speak the SAY line as you perform the DO. Don't click ahead of the words.

**Pre-recording checklist**

- Controller running (`mas-lab serve` / `docker compose up`) with the **library-samples** library selected (it contains `trip-planner` and the three moderator overlays).
- Confirm the three overlays exist: `react-moderator`, `cot-moderator`, `reflection-moderator`.
- Confirm the pipeline **`pipeline-test`** exists (`library-samples/pipelines/pipeline-test.yaml`) and opens in the builder.
- Have the `trip-planner` dataset available for the experiment's Dataset field.
- Dark mode (default), zoom ~110–125%, bookmarks hidden, 1080p+.
- A short QA prompt ready to paste into the chat drawer.
- The experiment + pipeline take time — either let them finish or pre-run once so you can cut to a completed state without dead air.

---

## Scene 0 — Cold open & framing (0:00 – 0:25)

> **DO** — MAS-Lab Studio open on the **Applications** page, static hold.
> **SAY** — "Multi-agent systems are easy to prototype and hard to trust. But the moment you need more than one agent — or want to take it to production — you're hand-writing long YAML manifests and fighting their field structure."

> **DO** — Slow cursor drift across the page.
> **SAY** — "MAS-Lab solves that issue. You design the system visually on a canvas, and it generates the underlying manifests for you — schema-valid every time. And because the result is a genuine specification, you can run, benchmark, and visualize it from a single environment. Let's walk through it end to end."

---

## Scene 1 — Orientation (0:25 – 1:00)

> **DO** — Open the **TopBar library switcher**, select the **library-samples** lab.
> **SAY** — "One docker compose up started both this UI and the controller behind it. Everything is scoped to a library switchable right here. We're using the samples library."

> **DO** — Move the cursor down the **left sidebar**, pausing on each item.
> **SAY** — "Applications are already saved systems; let's build a new one from scratch."

---

## Scene 2 — Build a simple QA MAS (single agent) (1:00 – 2:10)

_Keep it small on purpose — one agent — so the authoring loop is crystal clear. One node = one beat._

> **DO** — Click **Add Application** (or **Playground**) → blank CanvasBuilder appears.
> **SAY** — "This is the Playground, where we'll build a simple single-agent question-answering system to show the workflow."

> **DO** — Drag the **Agent** 🤖 node onto the canvas and name it (e.g. `qa_agent`) with a one-line instruction.
> **SAY** — "We drop in an agent, name it, and give it a short instruction — answer the user's question. Notice the typed config panel: the fields are enforced, so we're never guessing the schema."

> **DO** — Drag the **Model** 🧠 node; connect it to the agent.
> **SAY** — "We wire in a model."

> **DO** — Drag a **Tools** 🔧 node; pick a web-search tool; connect it to the agent.
> **SAY** — "We give it a web-search tool, so the agent can look things up instead of relying only on what the model already knows."

> **DO** — Drag a **Prompt Skills** 📖 node; connect it.
> **SAY** — "And a reusable skill from the library, so we're referencing shared instructions instead of duplicating prompts."

> **DO** — Drag the **Text Input** 📝 node; wire it to the agent; type an example query (e.g. `What are the top attractions to visit in Paris?`).
> **SAY** — "And a text-input node marks where a question enters — say, 'What are the top attractions to visit in Paris?' That's a working MAS with one agent, built in under a minute."

---

## Scene 3 — Live graph → schema-valid YAML (2:10 – 2:45)

> **DO** — Click the **Yaml** tab; show the generated `mas.yaml` and `qa_agent.agent.yaml`.
> **SAY** — "Everything we dragged just became real manifests — a `mas.yaml` and an agent manifest — ready to commit."

> **DO** — Switch to **Graph**, change the model or instruction; switch back to **Yaml**; point at the changed line.
> **SAY** — "Edit the graph, and the YAML regenerates instantly — no drift between the picture and the spec."

> **DO** — Click **Validate**, then **Validate MAS**; show the pass alert.
> **SAY** — "And we validate against the JSON schemas — the same validation the CLI uses."

---

## Scene 5 — Save & run the QA MAS (3:10 – 3:40)

> **DO** — Click **Save** → fill name / description / intent → confirm; open it from **Applications**.
> **SAY** — "We save it with a name and an intent, and it lands in Applications alongside our other apps. Before committing, we can run the MAS right here to do a quick test. A tight design-and-test loop, without ever leaving the canvas. Now let's do something more interesting with a bigger system."

---

## Scene 6 — Meet the pre-built Trip Planner (3:40 – 4:20)

_Motivate why it's pre-made, and introduce the moderator — the agent the experiment will target._

> **DO** — In **Applications**, open **trip-planner**; the graph loads.
> **SAY** — "Real systems are bigger than one agent. Here's one we built earlier — a Trip Planner MAS — because wiring it live would take a while."

> **DO** — Point at the **moderator** node, then the three specialist nodes.
> **SAY** — "At the center is a moderator that orchestrates three specialist agents — a schedule agent, an itinerary agent, and a concierge agent. The moderator is the brain, and it's exactly what we want to experiment on."

> **DO** — Briefly show the **Yaml** tab, then return to Graph.
> **SAY** — "Same visual model, same generated manifests — just more of them. The question we care about: what's the best reasoning strategy for that moderator?"

---

## Scene 7 — Overlays: create one, then the three moderator patches (4:20 – 5:15)

_First state the ultimate goal, then show how an overlay is created and what it's for — build one quickly from a blank canvas. Then reveal that all three are already saved. Keep the live-create short; don't fully finish it._

> **DO** — Still on the **trip-planner** graph (or as you head to Overlays), gesture at the moderator.
> **SAY** — "The final goal is to build an experiment that tests variations of the system — different topology or design patterns on that moderator — and measures which one performs best. The building block for that is an overlay."

> **DO** — Go to **Overlays**; the table shows the three rows: `react-moderator`, `cot-moderator`, `reflection-moderator`.
> **SAY** — "Instead of forking the Trip Planner three times, we use overlays — small patches layered on top of the base system, one per reasoning strategy."

> **DO** — Click **New Overlay** → a blank OverlayBuilder canvas opens.
> **SAY** — "We start a new overlay on a blank canvas — same drag-and-drop model as the MAS itself."

> **DO** — Drag an **Agent** 🤖 node; set its target to `moderator`.
> **SAY** — "First, the target: which agent this patch applies to. We point it at the moderator."

> **DO** — Drag a **Design Pattern** 🔄 node; set it to **ReAct**; wire it to the agent node.
> **SAY** — "Then a design-pattern override — we'll pick ReAct — and wire it in. That's the whole overlay: change the moderator's reasoning strategy, and touch nothing else in the system."

> **DO** — Switch briefly to the overlay's **YAML** (or point at the generated patch), then navigate back to the **Overlays** table without saving.
> **SAY** — "And like everything else, it serializes to a small, schema-valid patch manifest. That's the purpose — a targeted, non-destructive change we can apply or remove without ever touching the base system."

> **DO** — Back on the table, gesture across the three existing rows.
> **SAY** — "We've already saved all three the same way — ReAct, Chain-of-Thought, and Reflection on the moderator."

---

## Scene 8 — Build & run the experiment: apply the 3 overlays over Trip Planner (5:05 – 6:15)

_State the goal out loud first, then fill the form field-by-field. This produces the execution traces — step one of the chain._

> **DO** — Go to **Experiments** → **Add Experiment**.
> **SAY** — "Now we turn those three overlays into a head-to-head experiment on the same Trip Planner running on a dataset, and we measure which reasoning strategy comes out ahead."

> **DO** — Set **Name** (e.g. `moderator-design-patterns`) and a **Description**.
> **SAY** — "Let's give it a name, moderator-design-patterns."

> **DO** — Check the **Use Patch Overlays** checkbox.
> **SAY** — "We switch on Patch Overlays — that's the mode where scenarios are the base MAS plus an overlay."

> **DO** — In **Base MAS Application**, select **trip-planner**.
> **SAY** — "The base MAS is the Trip Planner."

> **DO** — Scenario 1: set **ID** `react`, pick Overlay **global/react-moderator**. Click **+** to add a row.
> **SAY** — "Scenario one: the ReAct overlay."

> **DO** — Scenario 2: **ID** `cot`, Overlay **global/cot-moderator**. Add another row.
> **SAY** — "Scenario two: Chain-of-Thought."

> **DO** — Scenario 3: **ID** `reflection`, Overlay **global/reflection-moderator**.
> **SAY** — "And scenario three: Reflection. Three variants of the same system, defined by which overlay is attached."

> **DO** — Select the **Dataset** (the `trip-planner` dataset); leave Execution/Emulation at defaults.
> **SAY** — "We point it at the trip-planner dataset which contains the cases all three will be scored on, and keep the default run settings."

> **DO** — Optionally click the **YAML** tab in the modal to show the generated experiment spec, then back to **Form**; click **Save**.
> **SAY** — "And again — we filled a form, but it generated a complete, schema-valid experiment manifest. We save and run the experiment"

> **DO** — Click **Run** on the experiment row; the status/progress starts (let it reach completion or cut).
> **SAY** — "Running it launches all three scenarios as a benchmark. This is step one of the chain: it produces the raw execution traces for each variant. But traces aren't charts yet — for metrics and plots, we build a pipeline on top of this experiment."

---

## Scene 9 — Open the pre-built pipeline, walk its two branches, run it (6:15 – 7:05)

_Second link in the chain. Open the existing **`pipeline-test`** (non-trivial, so it's pre-made) and explain it by its two branches rather than step-by-step — trace a finger along each as you talk. Then run it._

> **DO** — In the sidebar, click **Pipelines** → open **`pipeline-test`** in the PipelineBuilder.
> **SAY** — "A pipeline transforms those raw traces into a meaningful analysis. This one's already built for our experiment, and it splits into two branches."

> **DO** — Trace the **extract-trajectories → extract-trace-stats / plot-multilevel-trajectory** branch.
> **SAY** — "The first one is observability: it extracts each trajectory run — what actually happened, step by step — then produces trace statistics and an interactive plot of how the moderator and its specialists handed work back and forth."

> **DO** — Trace the **eval-mce → collect-metrics → compute-ci → plotnine** branch.
> **SAY** — "The second is evaluation: an LLM judge scores every run, the scores are collected across all three scenarios, reduced to means with 95% confidence intervals, and plotted — the ReAct-versus-CoT-versus-Reflection comparison, as a figure."

> **DO** — Click **Run** on the `pipeline-test` row; watch status reach complete; point at the **Output** column.
> **SAY** — "Again it's just a schema-valid pipeline spec underneath. We run it against the experiment's output and it writes back the trajectories, metrics, and plots — and now there's a complete picture to open."

---

## Scene 10 — Open the experiment output: compare the three patterns (7:05 – 7:55)

_Payoff. Attribute each asset: traces from the experiment run, metrics/plots/analysis from the pipeline run — all in one output view, comparing ReAct vs CoT vs Reflection._

> **DO** — Go to **Experiments** → open the **experiment**; the results viewer loads (file tree left, viewer right).
> **SAY** — "We open the experiment's output. Because the experiment and its pipeline ran, everything they produced is exported here together — for all three variants."

> **DO** — In the file tree, open a scenario's **`events.jsonl`**; show the trace.
> **SAY** — "The benchmark records a full event trace for each variant."

> **DO** — Open the **`multilevel_trajectory`** HTML output (from the `plot-multilevel-trajectory` step); let the interactive diagram fill the screen.
> **SAY** — "This multilevel trajectory plot shows how the moderator delegated to its specialist agents during a representative execution — the full agent interaction flow in one diagram."

> **DO** — Open the **`plot.png`** comparison chart (from the `plotnine` step — "Scenario Comparison by Metric, 95% CI").
> **SAY** — "And this chart ranks the three head to head, plotting mean scores per metric with 95% confidence intervals. The pipeline generates it as a reproducible output. That's MAS-Lab — from a picture on a canvas to a multi-agent system you can test, compare, and trust."

---

## Scene 11 — Breadth & close (7:55 – 8:20)

> **DO** — Fast pan: **Datasets**, **Control Panel** — a couple of seconds each.
> **SAY** — "There's more in the same spirit — datasets, and a control panel for the runtime."

> **DO** — Return to the **Applications** page and hold.
> **SAY** — "Same idea throughout: build it visually, patch it with overlays, run it, and see the results — all from schema-valid specs. That's MAS-Lab — from a picture on a canvas to a multi-agent system you can test, compare, and trust. It's all open source; links are in the description."

---

## Appendix — the dependency chain (why the order is fixed)

```
Build QA MAS ─▶ Run  │  (Trip Planner + moderator overlays are PRE-BUILT)
                     ▼
       Run Experiment (Trip Planner × {react, cot, reflection} overlays)
                     │  produces ▶ execution traces (per variant)
                     ▼
       Open + Run pre-built Pipeline `pipeline-test` (reads that experiment's output)
                     │  produces ▶ trajectories · trace stats · MCE metrics · CIs · comparison plot
                     ▼
       Open Experiment output  ─▶  traces + pipeline assets, exported together
```

You cannot open meaningful results until **both** the experiment run (traces) **and** the pipeline run (metrics/plots/analysis) have completed — which is why the pipeline is built and run _before_ Scene 10.

## Appendix — shot list quick reference

| #   | Screen                           | Action                                                                       | Message                                                         |
| --- | -------------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------- |
| 0   | Applications                     | Static hold                                                                  | Problem framing                                                 |
| 1   | TopBar + Sidebar                 | Select library-samples, nav sweep                                            | Orientation                                                     |
| 2   | Playground / CanvasBuilder       | Build 1-agent QA MAS                                                         | Visual authoring, fast                                          |
| 3   | Yaml tab + Validate              | Graph→YAML sync, validate                                                    | Schema-valid manifests                                          |
| 4   | AgentChatDrawer                  | Ask a question                                                               | Live design-test loop                                           |
| 5   | Save → Applications → Run MAS    | Save, open, run                                                              | Versioned, runnable MAS                                         |
| 6   | Application: trip-planner        | Open pre-built MAS, show moderator + specialists                             | Real systems are bigger; meet the moderator                     |
| 7   | Overlays + OverlayBuilder        | New Overlay → build one (agent + design-pattern node), then show the 3 saved | How to create an overlay + its purpose                          |
| 8   | Experiments (Add + Run)          | Use Patch Overlays, base=trip-planner, 3 overlay scenarios, run              | Experiment run → **traces**                                     |
| 9   | Pipelines → open `pipeline-test` | Walk the 2 branches (observability + evaluation), then Run                   | Explain what it does; pipeline run → **metrics/plots/analysis** |
| 10  | Experiment detail                | Trace (run) → CSV + report (pipeline), compare patterns                      | Both assets exported together                                   |
| 11  | Datasets/Control Panel + close   | Fast pan                                                                     | Breadth + outro                                                 |

**Pacing note:** Scenes 2, 7, 8, and 10 are the "wow" beats — give them room; trim Scenes 1 and 11 if you run long. Keep DO and SAY locked together: perform the action _as_ you speak its line, never before.
