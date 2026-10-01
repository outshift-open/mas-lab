#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-memory snapshot identity and session-scoped snapshot tree.

A Snapshot is a cheap in-memory node. A Checkpoint is that node written
to disk. Walking the tree moves a debug cursor; it does not change the
live run until someone promotes a branch.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SnapshotRef:
    """Identity of one snapshot node. ``snapshot_id`` is a content hash."""

    snapshot_id: str
    session_id: str
    parent_snapshot_id: str | None
    turn: int
    taken_at: str
    spec_revision: int | None = None
    label: str = ""

    @classmethod
    def from_state(
        cls,
        *,
        session_id: str,
        parent_snapshot_id: str | None,
        turn: int,
        kernel: dict[str, Any],
        working_memory: Any,
        spec_revision: int | None = None,
        label: str = "",
    ) -> SnapshotRef:
        taken_at = datetime.now(UTC).isoformat()
        snapshot_id = _canonical_hash(
            {
                "kernel": kernel,
                "working_memory": working_memory,
                "spec_revision": spec_revision,
                "turn": turn,
            }
        )
        return cls(
            snapshot_id=snapshot_id,
            session_id=session_id,
            parent_snapshot_id=parent_snapshot_id,
            turn=turn,
            taken_at=taken_at,
            spec_revision=spec_revision,
            label=label,
        )


@dataclass
class Snapshot:
    """In-memory capture. Never expected to cross a process boundary."""

    ref: SnapshotRef
    kernel: dict[str, Any]
    working_memory: list[Any]
    spec: dict[str, Any] | None = None
    spec_revision: int | None = None


class SnapshotTree:
    """Per-session tree of snapshot refs. Live trajectory ≠ debug cursor."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, SnapshotRef]] = {}
        self._live: dict[str, str] = {}
        self._cursor: dict[str, str] = {}
        self._bodies: dict[str, Snapshot] = {}

    def record(self, ref: SnapshotRef, *, body: Snapshot | None = None, live: bool = True) -> None:
        bucket = self._nodes.setdefault(ref.session_id, {})
        bucket[ref.snapshot_id] = ref
        if body is not None:
            self._bodies[ref.snapshot_id] = body
        if live:
            self._live[ref.session_id] = ref.snapshot_id
            if ref.session_id not in self._cursor:
                self._cursor[ref.session_id] = ref.snapshot_id

    def get(self, snapshot_id: str) -> SnapshotRef | None:
        for bucket in self._nodes.values():
            if snapshot_id in bucket:
                return bucket[snapshot_id]
        return None

    def body(self, snapshot_id: str) -> Snapshot | None:
        return self._bodies.get(snapshot_id)

    def children(self, snapshot_id: str) -> list[SnapshotRef]:
        parent = self.get(snapshot_id)
        if parent is None:
            return []
        bucket = self._nodes.get(parent.session_id, {})
        return [ref for ref in bucket.values() if ref.parent_snapshot_id == snapshot_id]

    def path_to_root(self, snapshot_id: str) -> list[SnapshotRef]:
        path: list[SnapshotRef] = []
        current = self.get(snapshot_id)
        seen: set[str] = set()
        while current is not None and current.snapshot_id not in seen:
            path.append(current)
            seen.add(current.snapshot_id)
            current = self.get(current.parent_snapshot_id) if current.parent_snapshot_id else None
        path.reverse()
        return path

    def all_branches(self, session_id: str) -> list[list[SnapshotRef]]:
        bucket = self._nodes.get(session_id, {})
        leaves = [
            ref
            for ref in bucket.values()
            if not any(child.parent_snapshot_id == ref.snapshot_id for child in bucket.values())
        ]
        if not leaves and bucket:
            leaves = list(bucket.values())
        return [self.path_to_root(leaf.snapshot_id) for leaf in leaves]

    def list_nodes(self, session_id: str) -> list[SnapshotRef]:
        bucket = self._nodes.get(session_id, {})
        return sorted(bucket.values(), key=lambda r: (r.turn, r.taken_at, r.snapshot_id))

    def live(self, session_id: str) -> SnapshotRef | None:
        sid = self._live.get(session_id)
        return self.get(sid) if sid else None

    def cursor(self, session_id: str) -> SnapshotRef | None:
        sid = self._cursor.get(session_id)
        return self.get(sid) if sid else None

    def set_cursor(self, session_id: str, snapshot_id: str) -> SnapshotRef:
        ref = self._nodes.get(session_id, {}).get(snapshot_id) or self.get(snapshot_id)
        if ref is None:
            raise KeyError(f"unknown snapshot {snapshot_id!r}")
        self._cursor[session_id] = ref.snapshot_id
        return ref

    def set_live(self, session_id: str, snapshot_id: str) -> SnapshotRef:
        ref = self.set_cursor(session_id, snapshot_id)
        self._live[session_id] = ref.snapshot_id
        return ref

    def clear_session(self, session_id: str) -> None:
        bodies = self._nodes.pop(session_id, {})
        self._live.pop(session_id, None)
        self._cursor.pop(session_id, None)
        for snapshot_id in bodies:
            self._bodies.pop(snapshot_id, None)


def persist(snapshot: Snapshot, store: Any, *, manifest: dict[str, Any], lineage: dict[str, Any], backtrack_count: int = 0) -> Any:
    """Write a Snapshot through PLAN-02's CheckpointStore. Disk is optional."""
    from mas.runtime.session.state import ManifestRef

    ref = ManifestRef.from_content(manifest)
    payload = {
        "version": 2,
        "label": snapshot.ref.label,
        "turn": snapshot.ref.turn,
        "backtrack_count": backtrack_count,
        "spec_revision": snapshot.spec_revision,
        "lineage": lineage,
        "kernel": snapshot.kernel,
        "working_memory": snapshot.working_memory,
        "manifest": {"content": ref.content, "content_hash": ref.content_hash},
    }
    label = snapshot.ref.label or f"turn-{snapshot.ref.turn:04d}"
    return store.save(payload, label=f"{snapshot.ref.session_id}-{label}")
