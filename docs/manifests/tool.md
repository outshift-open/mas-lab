<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tool manifest (`kind: Tool`)

**Package:** `mas-runtime` · **Schema:** [`tool.schema.yaml`](../schemas/runtime/tool.schema.yaml) · **apiVersion:** `mas/v1`

A **Tool** manifest is the declarative advertise contract of **one** tool: name,
parameters, optional protocol extras, and an `impl` pointer. Agents reference it
via `spec.tools[].ref`. The Python class behind `impl` implements
[`ToolContract`](../references/tool-contract.md).

**Related:** [ToolContract](../references/tool-contract.md) · [Agent](agent.md) ·
[Infra `ToolServerRegistry`](infra.md#toolserverregistry) · [ToolBundle](runtime.md#tool-family)

A Tool document that only declares `parameters` + `impl` is valid.
Every field below **title** is optional.

---

## Shape

```yaml
apiVersion: mas/v1
kind: Tool
metadata:
  name: web-search          # call name (required)
  description: Catalogue one-liner
spec:
  description: >            # LLM / tool-server description
    Search the web. Call this when the user needs current information.
  parameters:
    - name: query
      type: string
      required: true
  returns:                  # short daily-ops return note
    type: object
    description: Dict with query, results, cached
  impl:
    kind: python
    module_path: ./web_search_tool.py
    class_name: WebSearchTool
```

Annotated example with every optional advertise field:
[`schemas/examples/tools/annotated.tool.yaml`](../schemas/examples/tools/annotated.tool.yaml).

---

## Required vs optional

| Field | Required | Notes |
|-------|----------|--------|
| `metadata.name` | yes | Call name (`call_tool` first argument) |
| `spec.description` | no (default `""`) | LLM-facing text |
| `spec.parameters[]` | no (default `[]`) | JSON Schema `properties` |
| `spec.impl.module_path` | yes when loading | Hidden from the LLM |
| `spec.returns` | no | Short `{type, description}` — not a full JSON Schema |
| `spec.idempotent` | no (default `false`) | Retry hint |
| `spec.timeout_seconds` | no (default `30`) | Wall-clock cap |
| `spec.title` | no | Display name distinct from `metadata.name` |
| `spec.output_schema` | no | Full JSON Schema for the result (MCP `outputSchema`) |
| `spec.read_only` | no | Omit = unspecified, not `false` |
| `spec.destructive` | no | Omit = unspecified |
| `spec.open_world` | no | Omit = unspecified |
| `spec.icons[]` | no | `{src, mime_type, sizes, theme}` |
| `spec.task_support` | no | `forbidden` \| `optional` \| `required` |
| `spec.meta` | no | Advertise `_meta` for protocol adapters |
| `spec.execution_mode` | no (default `sync`) | `sync` \| `async` \| `realtime` |
| `spec.result_mode` | no (default `inline`) | `inline` \| `stream` \| `session` |
| `spec.events` | no | Stream/session event descriptors |
| `spec.tool_category` | no | Catalogue grouping |

`read_only` / `destructive` / `open_world` use three-state YAML: omit the key
to leave the hint unspecified. `false` is an explicit hint.

---

## What does **not** belong here

Connection and list-transport policy are **infra**, not the tool:

| Concern | Manifest |
|---------|----------|
| URL, SSE vs stdio, HTTP headers, call timeout for a remote server | `infra/v1` `kind: ToolServerRegistry` |
| Which names this agent claims (`*` vs `[web-search]`) | `Agent` / Overlay `spec.providers[]` |
| Implementation class | `spec.impl` on this document |

See [infra.md — ToolServerRegistry](infra.md#toolserverregistry).

---

## Omitted keys

- YAML may omit every optional key (`additionalProperties: false` rejects
  **unknown** keys only).
- `ToolDocument.from_dict` defaults unset advertise fields to empty / `None`.
- `list_tools()` returns `{name, description, parameters}` when optionals are
  unset. YAML extras are merged onto that dict when present.

---

## See also

- Schema: [`tool.schema.yaml`](../schemas/runtime/tool.schema.yaml)
- Bundle entries: [`tool_bundle.schema.yaml`](../schemas/runtime/tool_bundle.schema.yaml)
- Contract: [tool-contract.md](../references/tool-contract.md)
- Infra: [tool-server-registry.md](../references/tool-server-registry.md)
