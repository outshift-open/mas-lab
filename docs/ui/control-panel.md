<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Control Panel

The Control Panel is a read-only view of the server-side configuration backing your library —
**infra** providers, **flavours**, and workspace files — plus the runtime runners the controller
currently has available. It's an inspection and debugging tool, not an editor: everything shown
here is loaded from files on the controller. In the sidebar it's the last item: Applications →
Playground → Experiments → Pipelines → Datasets → Overlays → **Control Panel**.

## Where to find it

- `/:library/control-panel`

## What you can do here

At the top of the page, when the controller reports any, a line lists the available **Runtime
runners** by id.

Below that, three tabs each show a file selector and a read-only YAML viewer:

- **Infra** — infra manifests (`LLMProxy`, `ToolRegistry`, secrets mapping, etc.)
- **Flavours** — flavour manifests (deployment presets for protocol, observability, tool policy)
- **Workspace** — other workspace configuration files

Pick a file from the tab's dropdown to view its contents rendered as YAML. If a tab has no files
for the current library, it shows a "No \<tab\> configuration files available" message instead.

!!! note
    Nothing on this page is editable or saveable — there's no form, no save button, and no way to
    change these files from the UI. Use it to answer questions like "why did my run use this
    model provider" by inspecting the actual infra/flavour/workspace files the controller is
    reading, then edit the underlying manifests directly (or through the Overlays/Applications
    pages, where applicable) if something needs to change.

## Task walkthrough

Inspect the infra config backing your runs:

1. Open **Control Panel** from the sidebar.
2. Select the **Infra** tab.
3. Use the file dropdown to choose the infra manifest you want to check (for example, the
   `LLMProxy` or `ToolRegistry` file referenced by your MAS or experiment).
4. Read the rendered YAML to confirm the proxy URL, model catalogue, tool registry paths, or
   secrets mapping actually in effect.
5. Switch to **Flavours** or **Workspace** the same way to cross-check the deployment profile or
   other workspace files, and check the **Runtime runners** line at the top if you need to confirm
   which runners the controller currently exposes.

## Related

- [Infra manifest](../manifests/infra.md)
- [Flavour manifest](../manifests/flavour.md)
- [Web UI overview](index.md)
