#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ControlContract: pause is real, queue is FIFO, tree walk is traced."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mas.ctl.session.controller import SessionController
from mas.ctl.session.manager import SessionManager
from mas.ctl.session.turn_queue import TurnInputQueue
from mas.runtime.boundary.control.contract import (
    ControlCapability,
    ControlDenied,
    SessionPaused,
)
from mas.runtime.session import Session, SessionLineage, SessionStatus
from mas.runtime.session.snapshot import SnapshotRef, SnapshotTree


from mas.runtime.driver.mocks import AutoCtxAssembler


def _session(manager: SessionManager, session_id: str = "s1") -> Session:
    ctx = AutoCtxAssembler()
    instance = SimpleNamespace(
        snapshot=lambda: {"q": {}, "run": {}},
        load_checkpoint=lambda data: None,
        pause=lambda **kw: None,
        resume=lambda: None,
        driver=SimpleNamespace(ctx=ctx),
        feed=lambda event: SimpleNamespace(client_responses=[], hitl_requests=[], boundary_errors=[]),
    )

    class _Display:
        def on_system(self, *_a, **_k):
            return None

        def on_user(self, *_a, **_k):
            return None

    controller = SessionController(instance=instance, display=_Display())
    return manager.create(instance, controller, {"name": "agent", "spec": {}}, session_id=session_id)


def test_pause_blocks_the_next_user_turn() -> None:
    manager = SessionManager()
    session = _session(manager)
    control = manager.control(capability=ControlCapability(actor="admin", surface="admin"))
    control.pause("s1", reason="breakpoint")
    assert session.status is SessionStatus.PAUSED
    with pytest.raises(SessionPaused, match="paused"):
        session.controller.run_turn("hello")
    control.resume("s1")
    # no pause error — instance.feed is not a full driver, so we only care pause lifted
    session.controller._reject_if_paused()
    assert session.status is SessionStatus.ACTIVE
    kinds = [e.kind for e in manager.control_events]
    assert kinds == ["session_paused", "session_resumed"]
    assert manager.control_events[0].surface == "admin"


def test_queue_fifo_reorder_and_cancel() -> None:
    queue = TurnInputQueue()
    first = queue.enqueue("s1", "one", source="a")
    second = queue.enqueue("s1", "two", source="a")
    third = queue.enqueue("s1", "three", source="a")
    queue.reorder("s1", [third, first, second])
    queue.cancel("s1", first)
    assert [item.text for item in queue.peek("s1")] == ["three", "two"]
    assert queue.pop("s1").text == "three"
    assert queue.pop("s1").text == "two"
    assert queue.pop("s1") is None
    queue.enqueue("s1", "x", source="a")
    queue.clear_session("s1")
    assert queue.peek("s1") == []


def test_list_and_navigate_tree_is_traced_even_when_denied() -> None:
    tree = SnapshotTree()
    root = SnapshotRef.from_state(
        session_id="s1",
        parent_snapshot_id=None,
        turn=0,
        kernel={"a": 1},
        working_memory=[],
    )
    child = SnapshotRef.from_state(
        session_id="s1",
        parent_snapshot_id=root.snapshot_id,
        turn=1,
        kernel={"a": 2},
        working_memory=[],
    )
    tree.record(root)
    tree.record(child)
    manager = SessionManager(snapshot_tree=tree)
    _session(manager)
    control = manager.control(
        capability=ControlCapability(actor="plugin", surface="plugin"),
        deny_navigate=lambda to: to == child.snapshot_id,
    )
    nodes = control.list_checkpoints("s1")
    assert {n.snapshot_id for n in nodes} == {root.snapshot_id, child.snapshot_id}
    children = [n.snapshot_id for n in tree.children(root.snapshot_id)]
    assert children == [child.snapshot_id]
    with pytest.raises(ControlDenied):
        control.navigate("s1", to=child.snapshot_id, reason="secret")
    denied = [e for e in manager.control_events if e.kind == "checkpoint_navigated"]
    assert denied and denied[0].denied is True
    assert tree.cursor("s1").snapshot_id == root.snapshot_id
    control.deny_navigate = None
    moved = control.navigate("s1", to=child.snapshot_id, reason="inspect")
    assert moved.snapshot_id == child.snapshot_id
    assert tree.cursor("s1").snapshot_id == child.snapshot_id
    assert tree.live("s1").snapshot_id == child.snapshot_id  # last record() set live to child
    view = control.inspect("s1")
    assert view.cursor_snapshot_id == child.snapshot_id


def test_capability_token_scopes_methods_and_sessions() -> None:
    manager = SessionManager()
    _session(manager, "s1")
    observer = manager.control(
        capability=ControlCapability(
            actor="observer",
            surface="llm",
            session_ids=frozenset({"s1"}),
            methods=frozenset({"inspect", "list_checkpoints"}),
        )
    )
    observer.inspect("s1")
    with pytest.raises(ControlDenied, match="capability"):
        observer.pause("s1", reason="no")
    with pytest.raises(ControlDenied):
        manager.control(
            capability=ControlCapability(actor="other", surface="admin", session_ids=frozenset({"other"}))
        ).inspect("s1")


def test_checkpoint_does_not_unpause_a_paused_session() -> None:
    manager = SessionManager()
    session = _session(manager)
    session.pause(reason="hold")

    class _Store:
        def save(self, snapshot, *, label=""):
            from pathlib import Path

            return Path("x.checkpoint.json")

        def retain(self, *args, **kwargs):
            return None

    session.checkpoint(_Store(), label="held")
    assert session.status is SessionStatus.PAUSED
