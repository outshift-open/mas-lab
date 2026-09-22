<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Overlays

An overlay is not a standalone manifest — it's a namespaced patch on top of an existing agent
or MAS, letting you override a design pattern, add or remove tools, or replace an agent's
instructions without duplicating the base manifest. This is how the tutorials build variants for
comparison (see `docs/tutorials/01-building-an-agent/overlays/`: `baseline.yaml` keeps the
control agent's tools, `cot.yaml` swaps in Chain-of-Thought reasoning, `tools.yaml` and
`memory.yaml` layer in extra capabilities) — the same base agent, patched several different ways,
so experiments can score each variant against the others. In the sidebar it sits between
**Datasets** and **Control Panel**: Applications → Playground → Experiments → Pipelines →
Datasets → **Overlays** → Control Panel.

## Where to find it

- `/:library/overlays` — the overlays table
- `/:library/overlays/new` and `/:library/overlays/new/:overlayTab` — create a new overlay
  (`:overlayTab` is `graph` or `yaml`)
- `/:library/overlays/:name` and `/:library/overlays/:name/:overlayTab` — view/edit an existing
  overlay

## What you can do here

**Overlays table.** Lists every overlay manifest in the library with its **Name**, **Namespace**,
and **Description**. Clicking a row's name opens it for editing. The row action menu offers
**Edit** and **Delete**; you can also select multiple rows and use **Delete Selected (N)**. Either
delete path opens a "Confirm Delete" dialog before removing anything. If there are no overlays
yet, the table shows an empty state: "Create an overlay to get started". Use **New Overlay** to
start one.

**Overlay editor.** Both the "new" and existing-overlay pages share the same **Overlay** / **YAML**
tabs:

- **Overlay** — a node-based canvas (React Flow) scoped to a single **Namespace** (selected from
  a dropdown at the top; defaults to Global). Drag node types from the side panel onto the
  canvas:
  - **Agent** — represents a target agent in the namespace; other nodes connect into it to build
    that agent's overrides.
  - **Design Pattern** — overrides the connected agent's `design_pattern` (`react`, `cot`, or
    `reflection`) and its `max_steps`.
  - **Tools (Add)** — appends tools to the connected agent's existing tool set (deduplicated).
  - **Tools (Remove)** — excludes tools from the connected agent's tool set.
  - **Instructions** — overrides the connected agent's `spec.context.role`.

  Connecting a node to an Agent node populates that agent's patch; switching the Namespace
  dropdown clears any Tools nodes, since tool choices are namespace-specific.
- **YAML** — a generated preview of the overlay manifest, shown as `<name>.overlay.yaml` (or
  `overlay.yaml` before it's named), built from the current graph. It's empty until at least one
  agent node has an override configured.

Both tabs share the same **Save** and **Validate** actions at the top of the page. **Validate**
checks the current YAML against the schema and shows a success or error alert. **Save** opens a
dialog ("Save Overlay" for a new overlay, "Save Overlay As" when editing) with **Overlay Name**
and **Description** fields; confirming writes the manifest and returns you to it under its saved
name.

!!! note
    An overlay only ever patches — it never defines a full agent from scratch. It's scoped to one
    namespace at a time (Global or a specific application), and the Tools nodes list tools
    available in whichever namespace is currently selected.

## Task walkthrough

Create a new overlay:

1. From the Overlays table, click **New Overlay**. The page title shows "New Overlay".
2. On the **Overlay** tab, pick the target **Namespace** from the dropdown (Global, or the
   application whose agents you want to patch).
3. Drag an **Agent** node onto the canvas and set it to the agent you want to override.
4. Drag in whichever override nodes you need — **Design Pattern**, **Tools (Add)**,
   **Tools (Remove)**, **Instructions** — and connect each one to the Agent node.
5. Switch to the **YAML** tab at any point to review the generated `*.overlay.yaml` patch.
6. Click **Validate** to check the manifest before saving.
7. Click **Save**, give it a name (and optional description) in the **Save Overlay** dialog, and
   confirm — this creates the overlay and takes you to its saved page.

## Related

- [Overlay manifest](../manifests/overlay.md)
- [Applications](applications.md)
- [Web UI overview](index.md)
