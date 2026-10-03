#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Per-session FIFO of pending turns. Mutations are lock-linearized.

Two callers (two A2A users, or A2A plus a control client) share one
queue per ``session_id``. A2A ``message/send`` is always tail
(``action="turn"``). Control may also insert at ``head`` or an
``inspect_queue`` index. Drop, reorder, and action changes are
compare-and-swap on a monotonic ``revision``: a stale peek fails with
``QueueConflict`` instead of last-write-wins. Mid-generation ``steer``
(preempt / replace) is not a queue mutation and not an A2A verb.
Waiting for the current generation to finish is ``steer(mode="after")``
(queue to front).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Literal

from mas.runtime.boundary.control.contract import (
    QueueAt,
    QueueConflict,
    QueueItemGone,
    QueueView,
    QueuedInputView,
)

QueuedAction = Literal["turn", "steer"]


def _insert_index(n: int, at: QueueAt) -> int:
    if at == "tail":
        return n
    if at == "head":
        return 0
    if isinstance(at, bool) or not isinstance(at, int):
        raise ValueError(
            f"enqueue at must be 'head', 'tail', or an index in [0, {n}], got {at!r}"
        )
    if at < 0 or at > n:
        raise ValueError(f"enqueue at={at} is out of range [0, {n}]")
    return at


@dataclass
class QueuedInput:
    input_id: str
    text: str
    source: str
    priority: int = 0
    action: QueuedAction = "turn"
    actor: str = ""


@dataclass
class _SessionQueue:
    items: list[QueuedInput] = field(default_factory=list)
    revision: int = 0


class TurnInputQueue:
    """Session-scoped turn queue. FIFO unless ``reorder`` is called.

    Concurrency contract:

    * One lock per session. Operations on different sessions do not block.
    * Linearization order is lock-acquisition order.
    * ``enqueue`` always succeeds (insert at ``at``, default tail) and
      bumps ``revision``. ``at`` is ``"head"``, ``"tail"``, or an index
      from ``inspect`` in ``[0, len]``. Queue-to-front is ``at="head"``.
    * ``cancel``, ``reorder``, and ``set_action`` take an optional
      ``revision``. If it does not match, they raise ``QueueConflict``.
    * An item that has already been ``pop``-ed raises ``QueueItemGone``.
    * ``pop`` is the only consumer; it runs under the same lock so a
      concurrent cancel cannot hit an item already handed to a turn.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionQueue] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._meta = threading.Lock()

    def _lock(self, session_id: str) -> threading.RLock:
        with self._meta:
            return self._locks.setdefault(session_id, threading.RLock())

    def _state(self, session_id: str) -> _SessionQueue:
        return self._sessions.setdefault(session_id, _SessionQueue())

    def _check_revision(self, state: _SessionQueue, revision: int | None) -> None:
        if revision is not None and revision != state.revision:
            raise QueueConflict(
                expected=revision,
                actual=state.revision,
            )

    def enqueue(
        self,
        session_id: str,
        text: str,
        *,
        source: str,
        priority: int = 0,
        action: QueuedAction = "turn",
        actor: str = "",
        at: QueueAt = "tail",
    ) -> str:
        input_id = str(uuid.uuid4())
        if action == "steer" and not text.startswith("/steer "):
            text = f"/steer {text}"
        with self._lock(session_id):
            state = self._state(session_id)
            index = _insert_index(len(state.items), at)
            state.items.insert(
                index,
                QueuedInput(
                    input_id=input_id,
                    text=text,
                    source=source,
                    priority=priority,
                    action=action,
                    actor=actor,
                ),
            )
            state.revision += 1
        return input_id

    def pop(self, session_id: str) -> QueuedInput | None:
        with self._lock(session_id):
            state = self._sessions.get(session_id)
            if state is None or not state.items:
                return None
            item = state.items.pop(0)
            state.revision += 1
            if not state.items:
                self._sessions.pop(session_id, None)
            return item

    def peek(self, session_id: str) -> list[QueuedInputView]:
        return list(self.inspect(session_id).items)

    def inspect(self, session_id: str) -> QueueView:
        with self._lock(session_id):
            state = self._sessions.get(session_id) or _SessionQueue()
            items = tuple(_view(item, state.revision) for item in state.items)
            return QueueView(session_id=session_id, revision=state.revision, items=items)

    def reorder(
        self,
        session_id: str,
        order: list[str],
        *,
        revision: int | None = None,
    ) -> int:
        with self._lock(session_id):
            state = self._state(session_id)
            self._check_revision(state, revision)
            by_id = {item.input_id: item for item in state.items}
            if set(order) != set(by_id):
                raise ValueError("reorder_queue order must list every queued id exactly once")
            state.items = [by_id[input_id] for input_id in order]
            state.revision += 1
            return state.revision

    def cancel(self, session_id: str, input_id: str, *, revision: int | None = None) -> int:
        with self._lock(session_id):
            state = self._sessions.get(session_id)
            if state is None:
                raise QueueItemGone(input_id)
            self._check_revision(state, revision)
            kept = [item for item in state.items if item.input_id != input_id]
            if len(kept) == len(state.items):
                raise QueueItemGone(input_id)
            state.revision += 1
            if kept:
                state.items = kept
            else:
                self._sessions.pop(session_id, None)
            return state.revision

    def set_action(
        self,
        session_id: str,
        input_id: str,
        *,
        action: QueuedAction,
        revision: int | None = None,
    ) -> int:
        """Change a still-queued item from ``turn`` to ``steer`` (or back)."""
        with self._lock(session_id):
            state = self._sessions.get(session_id)
            if state is None:
                raise QueueItemGone(input_id)
            self._check_revision(state, revision)
            for item in state.items:
                if item.input_id == input_id:
                    item.action = action
                    if action == "steer" and not item.text.startswith("/steer "):
                        item.text = f"/steer {item.text}"
                    state.revision += 1
                    return state.revision
            raise QueueItemGone(input_id)

    def clear_session(self, session_id: str) -> None:
        with self._lock(session_id):
            self._sessions.pop(session_id, None)
            with self._meta:
                self._locks.pop(session_id, None)


def _view(item: QueuedInput, revision: int) -> QueuedInputView:
    return QueuedInputView(
        input_id=item.input_id,
        text=item.text,
        source=item.source,
        priority=item.priority,
        action=item.action,
        actor=item.actor,
        revision=revision,
    )
