<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Thin waist — one registry per job

Agent-selectable behaviour is resolved by **name → implementation** in
`PluginRegistry` (manifest `spec.*` keys). Embedder-chosen infra
(runtime, placement, framework) is resolved from
`component-registry.yaml`. A third table that maps the same names is a
duplicate.

## PluginRegistry

Manifest plugin types (`design_pattern`, `governance`, `llm_provider`,
`skill_impl`, …) load through `PluginRegistry.resolve_by_type`. Skills
use `skill_impl` rows in `library.yaml`; there is no parallel
`SkillPluginRegistry` implementation table.

Boundary slots are a closed set. `register_type(..., layer="boundary")`
rejects unknown envelope types. Library types (`related_state`,
`execute_sandbox`, `circuit_breaker`, `skill_*`, lab steps) are not envelope slots.

## Component catalog

Framework adapters and placement backends start empty and are filled
from the catalog. Unknown ids fail through `validate_component_id` /
`get_framework_adapter`. Docker and Kubernetes placement remain
`status: planned` until an availability plugin is declared.

## Control and snapshots

Pause, navigate, spec revision, and snapshot storage are
`ControlContract` / `SnapshotTree` APIs, not extra plugin-type enums.
The JSON-lines control wire is a library `control_protocol` plugin.
A2A session attach is `agent_expose`: `contextId` is the session id.
User turns on that session are `ControlContract.send_message` (A2A
`message/send`). `AgentCommContract` is outbound peer send after
delegation, not inbound user input.
