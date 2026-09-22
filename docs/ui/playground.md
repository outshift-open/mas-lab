<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Playground

**Playground** is where you author a new MAS (multi-agent system) from an
empty canvas. It builds the same [MAS manifest](../manifests/mas.md)
(`mas.yaml`) and [Agent manifests](../manifests/agent.md) as
[Applications](applications.md), but starts with nothing saved yet — saving
here creates a brand-new Application. In the sidebar it sits right after
Applications, ahead of Experiments, Pipelines, Datasets, Overlays, and
Control Panel.

## Where to find it

- `/:library/playground` (defaults to the Graph tab) or
  `/:library/playground/:playgroundTab` (`graph` or `yaml`)

## What you can do here

The page embeds the same drag-and-drop canvas editor (React Flow) as the
Applications detail page, starting from a blank graph:

- **Sidebar node palette** — drag **Agent**, **Model**, **Design Pattern**,
  **Tools**, **Prompt Skills**, **Context Skills**, **Memory**, or
  **Text Input** nodes onto the canvas. Each of the seven non-Agent types
  connects into a specific input handle on an Agent node (model, design
  pattern, tools, prompt skills, context skills, memory, text input); an
  Agent's output can also connect into another Agent's Text Input handle to
  create a delegation edge between two agents.
- **Agent chat** — clicking an agent node's chat action opens a drawer to
  run a live conversation against that agent's current manifest, useful for
  sanity-checking a single agent before wiring it into a larger workflow.
- **Yaml tab** — read-only, syntax-highlighted `mas.yaml` and one
  `<agent>.agent.yaml` block per agent, regenerated live as you edit the
  graph (the entry agent and sequential/dynamic workflow type are inferred
  automatically from how agents are connected).
- **Validate** / **Validate MAS** — validate the selected agent's manifest,
  or the whole `mas.yaml`, before saving.
- **Save** — opens a "Save MAS" dialog (MAS Name, Description, Intent) and
  creates a new Application with those manifests.

!!! note "No Run action"
    Playground has **Save**, **Validate**, and **Validate MAS**, but no
    "Run MAS" button — it's for authoring and validating a MAS, not
    launching it. Save the MAS, then open it from [Applications](applications.md)
    to run it.

## Task walkthrough

**Build a new MAS from scratch:**

1. Go to **Applications** and click **Add Application** (or navigate to
   **Playground** directly) to land on an empty Graph tab.
2. Drag an **Agent** node from the sidebar onto the canvas for each
   participant you need.
3. Drag a **Model**, **Design Pattern**, **Tools**, **Prompt Skills**,
   **Context Skills**, or **Memory** node onto the canvas and connect it to
   the matching handle on an agent.
4. Add a **Text Input** node and connect it to the entry agent's text-input
   handle — this becomes the query used later when the MAS is run from
   Applications. For multi-agent flows, connect one agent's output to
   another agent's Text Input handle to define delegation.
5. Switch to the **Yaml** tab to review the generated `mas.yaml` and
   per-agent manifests.
6. Click **Validate** (with an agent selected) and **Validate MAS** to catch
   errors early.
7. Click **Save**, enter a **MAS Name** (required) plus optional
   **Description** and **Intent**, and click **Save** again. On success a
   confirmation banner appears and the new MAS is available from
   Applications.

## Related

- [MAS manifest](../manifests/mas.md)
- [Agent manifest](../manifests/agent.md)
- [Applications](applications.md) — browse, run, and manage saved MAS apps
- [Web UI overview](index.md)
