#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.runtime.session.snapshot import SnapshotRef, SnapshotTree
from mas.runtime.session.trajectory import (
    alternative_words,
    boolean_reaches,
    counterfactuals,
    llm_trajectory,
    tropical_root_cause,
)


def _node(tree: SnapshotTree, **kwargs) -> SnapshotRef:
    live = kwargs.pop("live", True)
    session_id = kwargs.setdefault("session_id", "s")
    kwargs.setdefault("kernel", {"n": kwargs.get("seq", 0)})
    kwargs.setdefault("working_memory", [])
    kwargs["seq"] = tree.next_seq(session_id)
    ref = SnapshotRef.from_state(**kwargs)
    tree.record(ref, live=live)
    return ref


def test_counterfactuals_are_siblings() -> None:
    tree = SnapshotTree()
    root = _node(tree, parent_snapshot_id=None, turn=0, kind="explicit")
    a = _node(
        tree,
        parent_snapshot_id=root.snapshot_id,
        turn=1,
        kind="governance",
        hook="egress",
        decision="ALLOW",
        op="TOOL_CALL",
        correlation_id=1,
    )
    b = _node(
        tree,
        parent_snapshot_id=root.snapshot_id,
        turn=1,
        kind="governance",
        hook="egress",
        decision="BLOCK",
        op="TOOL_CALL",
        correlation_id=2,
        live=False,
    )
    sibs = {ref.snapshot_id for ref in counterfactuals(tree, a.snapshot_id)}
    assert b.snapshot_id in sibs
    assert boolean_reaches(tree, root.snapshot_id, a.snapshot_id)
    cost, path = tropical_root_cause(tree, b.snapshot_id)
    assert cost == 1
    assert path[-1].decision == "BLOCK"
    words = alternative_words(tree, "s")
    assert any("BLOCK" in word for word in words)
    assert llm_trajectory(tree, a.snapshot_id) == []
