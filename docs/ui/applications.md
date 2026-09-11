<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Applications

**Applications** is the list of saved MAS (multi-agent system) apps in the current
library, and the detail view for editing one. Each app is backed by a
[MAS manifest](../manifests/mas.md) (`mas.yaml`) plus one [Agent manifest](../manifests/agent.md)
per participant. In the sidebar it is the first entry, ahead of Playground,
Experiments, Pipelines, Datasets, Overlays, and Control Panel.

## Where to find it

- List: `/:library/applications`
- Detail: `/:library/applications/:id` (defaults to the Graph tab) or
  `/:library/applications/:id/:applicationTab` (`graph` or `yaml`)

## What you can do here

**On the list page** you get a table of every saved MAS (Name, Description,
Intent, Agents tags). Clicking a row opens that app. The row action menu
(and the "Delete Selected" toolbar button for multi-row selection) offers:

- **Edit** — opens the app's detail page
- **Duplicate** — clones the MAS under a new name, description, and intent
- **Delete** — asks for confirmation, then removes the app

The **Add Application** button in the page header does not create an app
directly — it navigates to [Playground](playground.md), where a new MAS is
authored and saved.

**On the detail page** (opened from a row) you edit one MAS:

- **Graph** tab — the same node-based canvas editor used by Playground (see
  [Playground's canvas section](playground.md#what-you-can-do-here)), pre-loaded
  from the app's stored manifests
- **Yaml** tab — read-only, syntax-highlighted `mas.yaml` and one
  `<agent>.agent.yaml` block per agent, regenerated live from the graph
- **Save** — opens a "Save MAS" dialog (MAS Name, Description, Intent) and
  writes the edited manifests back to this app; renaming navigates to the new URL
- **Validate** — validates the currently selected agent's manifest (select an
  agent node on the Graph tab first)
- **Validate MAS** — validates the whole `mas.yaml`
- **Run MAS** — submits the MAS's entry agent as a job and polls it to
  completion, showing stdout/the agent's response on success, or stderr/the
  error on failure, in a dismissible banner

!!! note "Legacy single-agent sample apps"
    A few bundled sample apps ship as a bare `kind: Agent` manifest instead of
    `kind: MAS`. The detail page detects this and displays/edits them the same
    way, just without a `mas.yaml` — the Yaml tab shows only the single
    `agent:<name>` manifest, and actions that require a MAS (Run MAS, Validate
    MAS) have nothing to operate on.

## Task walkthrough

**Open and run an existing MAS:**

1. Go to **Applications** in the sidebar.
2. Click a row in the table to open its detail page.
3. On the **Graph** tab, confirm a **Text Input** node with content is wired
   into the entry agent — Run MAS uses that text as the query.
4. Optionally click **Validate MAS** to catch manifest errors first.
5. Click **Run MAS**. The button reads "Running MAS..." while the job is
   polled; when it finishes, the result (or error) appears as a banner at the
   top of the page.
6. If you changed the graph, click **Save**, fill in the **MAS Name**
   (required), **Description**, and **Intent** fields in the Save MAS dialog,
   and click **Save** again to persist the changes.

## Related

- [MAS manifest](../manifests/mas.md)
- [Agent manifest](../manifests/agent.md)
- [Playground](playground.md) — build a new MAS from scratch
- [Web UI overview](index.md)
