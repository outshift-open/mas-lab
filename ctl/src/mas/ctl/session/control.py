#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-process ControlContract over SessionManager.

Every verb takes a session id, checks a capability token, and appends a
ControlEvent. Plugin, LLM tool, and admin callers share this class and
differ only in ``ControlCapability.surface``.
"""

from __future__ import annotations

from typing import Any, Literal

from mas.runtime.boundary.control.contract import (
    ControlCapability,
    ControlDenied,
    ControlEvent,
    QueuedInputView,
    SessionPaused,
    SessionSnapshotView,
)
from mas.runtime.session import SessionStatus
from mas.runtime.session.snapshot import SnapshotRef, SnapshotTree


class SessionControl:
    """Default ControlContract implementation. Resolves ids through SessionManager."""

    def __init__(
        self,
        manager: Any,
        *,
        capability: ControlCapability | None = None,
        deny_navigate: Any | None = None,
    ) -> None:
        self._manager = manager
        self.capability = capability or ControlCapability(actor="in-process", surface="plugin")
        self.deny_navigate = deny_navigate
        self.events: list[ControlEvent] = manager.control_events

    def _require(self, method: str, session_id: str) -> Any:
        if not self.capability.allows(method, session_id):
            self._trace(method, session_id, kind="control_denied", denied=True, reason="capability")
            raise ControlDenied(method, session_id, reason="capability token does not allow this call")
        return self._manager.get(session_id)

    def _trace(
        self,
        method: str,
        session_id: str,
        *,
        kind: str,
        reason: str = "",
        payload: dict[str, Any] | None = None,
        denied: bool = False,
    ) -> ControlEvent:
        event = ControlEvent(
            kind=kind,
            session_id=session_id,
            actor=self.capability.actor,
            surface=self.capability.surface,
            method=method,
            reason=reason,
            payload=dict(payload or {}),
            denied=denied,
        )
        self.events.append(event)
        return event

    def pause(self, session_id: str, *, reason: str) -> None:
        session = self._require("pause", session_id)
        session.pause(reason=reason)
        self._trace("pause", session_id, kind="session_paused", reason=reason)

    def resume(self, session_id: str) -> None:
        session = self._require("resume", session_id)
        session.resume()
        self._trace("resume", session_id, kind="session_resumed")

    def steer(
        self,
        session_id: str,
        *,
        text: str,
        mode: Literal["inject_now", "enqueue"] = "inject_now",
    ) -> None:
        session = self._require("steer", session_id)
        if mode == "enqueue":
            self.enqueue_input(session_id, text=f"/steer {text}", source="steer")
            self._trace("steer", session_id, kind="steer_enqueued", payload={"text": text})
            return
        session.controller.run_turn(f"/steer {text}", auto_hitl=False)
        self._trace("steer", session_id, kind="steer_injected", payload={"text": text})

    def discard_last(self, session_id: str) -> str:
        session = self._require("discard_last", session_id)
        store = self._manager.checkpoint_store
        if store is None:
            raise RuntimeError("discard_last requires a checkpoint store")
        path = session.backtrack(store, steps=1)
        self._trace("discard_last", session_id, kind="checkpoint_restored", payload={"path": str(path)})
        return str(path)

    def inspect(self, session_id: str) -> SessionSnapshotView:
        session = self._require("inspect", session_id)
        tree: SnapshotTree = self._manager.snapshot_tree
        live = tree.live(session_id)
        cursor = tree.cursor(session_id)
        view = SessionSnapshotView(
            session_id=session_id,
            status=session.status.value,
            turn=int(getattr(session.controller, "_turn", 0)),
            live_snapshot_id=live.snapshot_id if live else None,
            cursor_snapshot_id=cursor.snapshot_id if cursor else None,
            spec_revision=getattr(session, "spec_revision", None),
        )
        self._trace(
            "inspect",
            session_id,
            kind="checkpoint_inspected",
            payload={"live": view.live_snapshot_id, "cursor": view.cursor_snapshot_id},
        )
        return view

    def list_checkpoints(self, session_id: str) -> list[SnapshotRef]:
        self._require("list_checkpoints", session_id)
        nodes = self._manager.snapshot_tree.list_nodes(session_id)
        self._trace(
            "list_checkpoints",
            session_id,
            kind="checkpoint_listed",
            payload={"count": len(nodes), "ids": [n.snapshot_id for n in nodes]},
        )
        return nodes

    def navigate(self, session_id: str, *, to: str, reason: str) -> SnapshotRef:
        self._require("navigate", session_id)
        tree: SnapshotTree = self._manager.snapshot_tree
        current = tree.cursor(session_id)
        if callable(self.deny_navigate) and self.deny_navigate(to):
            self._trace(
                "navigate",
                session_id,
                kind="checkpoint_navigated",
                reason=reason,
                payload={"from": current.snapshot_id if current else None, "to": to},
                denied=True,
            )
            raise ControlDenied("navigate", session_id, reason=reason or "navigate denied")
        ref = tree.set_cursor(session_id, to)
        self._trace(
            "navigate",
            session_id,
            kind="checkpoint_navigated",
            reason=reason,
            payload={"from": current.snapshot_id if current else None, "to": ref.snapshot_id},
        )
        return ref

    def enqueue_input(self, session_id: str, *, text: str, source: str, priority: int = 0) -> str:
        self._require("enqueue_input", session_id)
        input_id = self._manager.turn_queue.enqueue(
            session_id, text, source=source, priority=priority
        )
        self._trace(
            "enqueue_input",
            session_id,
            kind="input_enqueued",
            payload={"input_id": input_id, "source": source},
        )
        return input_id

    def peek_queue(self, session_id: str) -> list[QueuedInputView]:
        self._require("peek_queue", session_id)
        return self._manager.turn_queue.peek(session_id)

    def reorder_queue(self, session_id: str, order: list[str]) -> None:
        self._require("reorder_queue", session_id)
        self._manager.turn_queue.reorder(session_id, order)
        self._trace("reorder_queue", session_id, kind="queue_reordered", payload={"order": list(order)})

    def cancel_queued(self, session_id: str, input_id: str) -> None:
        self._require("cancel_queued", session_id)
        self._manager.turn_queue.cancel(session_id, input_id)
        self._trace("cancel_queued", session_id, kind="input_cancelled", payload={"input_id": input_id})

    def fork_investigation(self, session_id: str) -> str:
        session = self._require("fork_investigation", session_id)
        origin = session.take_snapshot(label="investigate-origin")
        child = session.take_snapshot(label="investigate", live=False)
        self._trace(
            "fork_investigation",
            session_id,
            kind="branch_opened",
            payload={
                "from": origin.ref.snapshot_id,
                "child": child.ref.snapshot_id,
                "parent_status": session.status.value,
            },
        )
        return child.ref.snapshot_id
