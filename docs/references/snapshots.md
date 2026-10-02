<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Snapshots vs checkpoints

A **snapshot** is a cheap in-memory picture of "where this run is":
kernel state, working memory, and the spec revision at that moment.
Taking one does not write disk.

A **checkpoint** is that picture saved so it can survive a process
restart. `persist(snapshot, store)` is the only bridge.

The pictures form a **tree**. Walking the tree (debug) moves a cursor.
That is not the same as the live run. Promoting a branch replaces the
live run. Discarding a `session.branch()` restores the origin.

Restore also restores the spec revision that was current at that node.
Otherwise replay would lie about which tools were enabled.

## Copy-on-write

- **Working memory:** freeze the live snapshot object (O(1)). The next
  `put` allocates a new unfrozen object. Export copies list/dict shells
  and shares string payloads. Do not `deepcopy` the conversation.
- **Kernel `QProduct`:** copy into a frozen `CowKernel` at snapshot time.
  Governance snapshots run *during* `transition`, so the live `q` must
  stay mutable. Kernel state is small; this is the right grain.
- **When:** at `GOVERNANCE_AUTHORIZE` / `GOVERNANCE_VALIDATE`, and on
  explicit `take_snapshot` / `branch`. Not every internal Mealy tick —
  those are not independently counterfactual.

`persist(snapshot)` is still the only disk path.

## Trajectory algebra

See `mas.runtime.session.trajectory`: counterfactuals = siblings;
root-cause = tropical weight on non-ALLOW edges; LLM trajectory = path
filtered to `LLM_CALL`. Not new kernel ops.
