<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Snapshots vs checkpoints

A **snapshot** is an in-memory node: kernel state, working memory, the
spec revision, and optional related-state fingerprints (execute
workspace). Taking one does not write disk.

A **checkpoint** is that node written so it survives a process restart.
`persist(snapshot, store)` is the only bridge. `mas-ctl control persist`
writes that file after the session is paused (or with `--auto-stop`);
another process resumes it with `mas-ctl checkpoint fork` then
`mas-ctl chat --load-checkpoint`. `mas-ctl control resume` only unpauses
the live session.

The nodes form a **tree**. Walking the tree moves a debug cursor. That
is not the live run. Promoting a branch replaces the live run.
Discarding `session.branch()` restores the origin.

Restore also restores the spec revision current at that node, so the
same tools are enabled as when the node was taken.

## Related workspace state

File bytes are not part of kernel product state. A `RelatedStatePlugin`
stores a fingerprint and locator on the snapshot. Adapters:

- **git** — `commit-tree` onto `refs/mas-lab/...` with a private index
  (does not move `HEAD` or the user index)
- **copy_dir** — content-hash directory copy (tests and hosts without git)

Restore replays those adapters. `SnapshotTree.from_events` rebuilds the
tree identity from trace events; bodies stay on the snapshot or adapter.

## When snapshots are taken

- Explicit `take_snapshot` / `branch`
- Governance ALLOW/DENY at authorize and validate (policy `governance`)

Working memory uses freeze-in-place. Kernel `QProduct` is copied into a
frozen `CowKernel` because governance snapshots run during a transition
that still mutates the live object.
