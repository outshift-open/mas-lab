<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Spawned subagents

`create_subagent` (alias `spawn_subagent`) is a **system tool**: the parent
LLM creates a specialist during a turn. It starts one pre-authored Agent
manifest for a single task and returns that child's final response as the
tool result. It differs from `delegate_to_<id>`: delegation calls a peer in
the MAS topology, while creating a subagent materializes a temporary child
from a named template.

## Enablement

Declaring the system tool is the whole contract: there is no separate
capability flag. An agent without this entry cannot spawn. Use either name:

```yaml
spec:
  tools:
    - kind: system
      name: create_subagent
      params:
        templates:
          - id: reviewer
            ref: ./agents/reviewer.yaml
            description: Review the proposed change
        max_spawns: 8
        max_depth: 3
```

The runtime advertises both `create_subagent` and `spawn_subagent` to the
model so it can "create a subagent" without a hidden host API. Template IDs
are unique within the manifest. References are containment-checked and must
resolve to valid Agent manifests. The model selects a declared template and
supplies its task; it cannot create a manifest or grant new tools at
runtime.

## Bounds and lifecycle

The default session budget allows eight child runs at a nesting depth of three.
`SpawnLedger` enforces both limits inside the ctl spawner. Each call materializes
one child, registers it on the local bus, runs one turn, returns the result, and
removes the instance and endpoint in a `finally` block. Parent-call identity is
preserved for trace attribution.

This release can run a child synchronously (one shot) or concurrently
when the async driver is enabled (`ainvoke`, `dispatch: parallel` on a
workflow). A child is torn down after its turn unless the session keeps
it. Bounds still apply.

See [Tutorial 9](../tutorials/07-subagents/README.md) for an incident
coordinator that creates researcher and reviewer specialists, and the
runnable [manifest pair](../schemas/examples/subagent-agent.yaml).
