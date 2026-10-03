#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Serialize concurrent user turns onto one session queue.

A2A maps ``contextId`` to ``session_id`` and ``message/send`` to
:meth:`SessionTurnMailbox.submit` (queue a turn at the tail). Two
connections without a context id are two sessions. Two connections that
reuse the same context id share this mailbox: enqueue is concurrent;
draining a turn is exclusive. This path never amends an in-flight
decode — that is control-protocol ``steer``.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future
from typing import Any, Callable

from mas.ctl.session.turn_queue import TurnInputQueue


class SessionTurnMailbox:
    """One FIFO per session. Callers wait for *their* queued item to run."""

    def __init__(self, queue: TurnInputQueue | None = None) -> None:
        self.queue = queue or TurnInputQueue()
        self._locks: dict[str, threading.RLock] = {}
        self._meta = threading.Lock()
        self._results: dict[str, Future[Any]] = {}

    def resolve_session_id(self, session_id: str | None) -> str:
        return str(session_id or "") or str(uuid.uuid4())

    def _lock(self, session_id: str) -> threading.RLock:
        with self._meta:
            return self._locks.setdefault(session_id, threading.RLock())

    def submit(
        self,
        session_id: str,
        text: str,
        *,
        source: str = "a2a",
        run: Callable[[str], Any],
        actor: str = "",
    ) -> Any:
        """A2A Send Message: enqueue a turn at the tail, then drain until it runs.

        Never calls ``steer`` / ``request_preempt``. Additional messages on a
        working task wait their turn. ``input-required`` is HITL, not this
        path.
        """
        input_id = self.queue.enqueue(
            session_id, text, source=source, actor=actor, action="turn", at="tail"
        )
        future: Future[Any] = Future()
        with self._meta:
            self._results[input_id] = future
        with self._lock(session_id):
            while not future.done():
                item = self.queue.pop(session_id)
                if item is None:
                    break
                pending = self._results.get(item.input_id)
                try:
                    result = run(item.text)
                    if pending is not None and not pending.done():
                        pending.set_result(result)
                except Exception as exc:
                    if pending is not None and not pending.done():
                        pending.set_exception(exc)
                    elif pending is None:
                        raise
        with self._meta:
            self._results.pop(input_id, None)
        return future.result()
