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
