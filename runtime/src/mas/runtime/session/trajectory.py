#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Trajectory algebra over a snapshot tree.

The kernel does not ship a solver. It ships the *carriers* a solver needs:
nodes (snapshots), parent edges, and labels taken at governance decisions.

Semirings (how to read the tree, not new kernel ops):

- **Boolean** — reachability. ``⊕ = or``, ``⊗ = and``.
  "Can this leaf see that authorize?"
- **Tropical / path** — root cause. ``⊕ = min``, ``⊗ = +``.
  Weight an edge by 1 if the decision was BLOCK/HITL, 0 if ALLOW; the
  shortest path from root to a failure is the cheapest explanation.
- **Sequence (free monoid)** — counterfactuals. ``⊗ = concat``, ``⊕ = set
  of alternative words``. Sibling children of one parent are the
  counterfactual set at that decision.

LLM calls are egress ``LLM_CALL`` edges. A trajectory of LLM calls is the
path filtered to ``op == LLM_CALL``. Scoring a genome (Ruflo Darwin) is
an algebra homomorphism from that path into the lab's semiring — still
not a kernel primitive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, TypeVar

from mas.runtime.session.snapshot import SnapshotRef, SnapshotTree

T = TypeVar("T")


@dataclass(frozen=True)
class PathEdge:
    """One parent → child step, labelled by the decision that created the child."""

    parent_id: str | None
    child_id: str
    hook: str
    decision: str
    op: str
    correlation_id: int
    kind: str
    turn: int

    @classmethod
    def from_ref(cls, ref: SnapshotRef) -> PathEdge:
        return cls(
            parent_id=ref.parent_snapshot_id,
            child_id=ref.snapshot_id,
            hook=ref.hook,
            decision=ref.decision,
            op=ref.op,
            correlation_id=ref.correlation_id,
            kind=ref.kind,
            turn=ref.turn,
        )


def path_edges(tree: SnapshotTree, snapshot_id: str) -> list[PathEdge]:
    """Root → node edges (the unique path in a tree)."""
    return [PathEdge.from_ref(ref) for ref in tree.path_to_root(snapshot_id)]


def counterfactuals(tree: SnapshotTree, snapshot_id: str) -> list[SnapshotRef]:
    """Sibling snapshots: the other outcomes of the same parent decision."""
    ref = tree.get(snapshot_id)
    if ref is None or ref.parent_snapshot_id is None:
        return []
    return [child for child in tree.children(ref.parent_snapshot_id) if child.snapshot_id != snapshot_id]


def llm_trajectory(tree: SnapshotTree, snapshot_id: str) -> list[PathEdge]:
    return [edge for edge in path_edges(tree, snapshot_id) if edge.op == "LLM_CALL"]


def fold_path(
    edges: Iterable[PathEdge],
    *,
    identity: T,
    times: Callable[[T, PathEdge], T],
) -> T:
    """``⊗`` along one path (the monoid of a semiring)."""
    acc = identity
    for edge in edges:
        acc = times(acc, edge)
    return acc


def boolean_reaches(tree: SnapshotTree, src: str, dst: str) -> bool:
    """Boolean semiring: dst is on the unique tree path from root through src, or src is an ancestor of dst."""
    path = {ref.snapshot_id for ref in tree.path_to_root(dst)}
    return src in path


def tropical_root_cause(
    tree: SnapshotTree,
    snapshot_id: str,
    *,
    weight: Callable[[PathEdge], int] | None = None,
) -> tuple[int, list[PathEdge]]:
    """Tropical semiring on a tree: the path *is* the unique explanation.

    Default weight: 1 for non-ALLOW governance, 0 otherwise. The total is
    how many policy interventions sit on the path to this node.
    """

    def default_weight(edge: PathEdge) -> int:
        if edge.kind != "governance":
            return 0
        if edge.decision in {"", "ALLOW", "LOG"}:
            return 0
        return 1

    weigh = weight or default_weight
    edges = path_edges(tree, snapshot_id)
    total = fold_path(edges, identity=0, times=lambda acc, edge: acc + weigh(edge))
    return total, edges


def alternative_words(tree: SnapshotTree, session_id: str) -> list[tuple[str, ...]]:
    """Free-monoid ⊕ of root→leaf decision words (counterfactual set)."""
    words: list[tuple[str, ...]] = []
    for path in tree.all_branches(session_id):
        words.append(tuple(ref.decision or ref.kind or ref.label for ref in path))
    return words
