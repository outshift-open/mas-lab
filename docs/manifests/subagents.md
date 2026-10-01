<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Spawned subagents

`spawn_subagent` starts one pre-authored Agent manifest for a single task and
returns its final response as the tool result. It differs from
`delegate_to_<id>`: delegation calls a peer in the MAS topology, while spawning
materializes a temporary child from a named template.

## Enablement

Declaring the system tool is the whole contract: there is no separate
capability flag. An agent without this entry cannot spawn.

```yaml
spec:
  tools:
    - kind: system
      name: spawn_subagent
      params:
        templates:
          - id: reviewer
            ref: ./agents/reviewer.yaml
            description: Review the proposed change
        max_spawns: 8
        max_depth: 3
```

Template IDs are unique within the manifest. References are containment-checked
and must resolve to valid Agent manifests. The model selects a declared
template and supplies its task; it cannot create a manifest or grant new tools
at runtime.

## Bounds and lifecycle

The default session budget allows eight child runs at a nesting depth of three.
`SpawnLedger` enforces both limits inside the ctl spawner. Each call materializes
one child, registers it on the local bus, runs one turn, returns the result, and
removes the instance and endpoint in a `finally` block. Parent-call identity is
preserved for trace attribution.

This release is synchronous and one-shot. A child is not retained for later
turns. Concurrent fan-out is gated on the async driver work in
[PLAN-04](../../../../PLAN-04-concurrency.md).

See [Tutorial 7](../tutorials/07-subagents/README.md) and the runnable
[manifest pair](../schemas/examples/subagent-agent.yaml).