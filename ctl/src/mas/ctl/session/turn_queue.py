#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Per-session FIFO of pending user turns. ``clear_session`` from day one."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from mas.runtime.boundary.control.contract import QueuedInputView


@dataclass
class QueuedInput:
    input_id: str
    text: str
    source: str
    priority: int = 0


class TurnInputQueue:
    """Session-scoped turn queue. FIFO unless ``reorder_queue`` is called."""

    def __init__(self) -> None:
        self._items: dict[str, list[QueuedInput]] = {}

    def enqueue(self, session_id: str, text: str, *, source: str, priority: int = 0) -> str:
        input_id = str(uuid.uuid4())
        self._items.setdefault(session_id, []).append(
            QueuedInput(input_id=input_id, text=text, source=source, priority=priority)
        )
        return input_id

    def pop(self, session_id: str) -> QueuedInput | None:
        items = self._items.get(session_id) or []
        if not items:
            return None
        item = items.pop(0)
        if not items:
            self._items.pop(session_id, None)
        return item

    def peek(self, session_id: str) -> list[QueuedInputView]:
        return [
            QueuedInputView(
                input_id=item.input_id,
                text=item.text,
                source=item.source,
                priority=item.priority,
            )
            for item in self._items.get(session_id, [])
        ]

    def reorder(self, session_id: str, order: list[str]) -> None:
        items = self._items.get(session_id) or []
        by_id = {item.input_id: item for item in items}
        if set(order) != set(by_id):
            raise ValueError("reorder_queue order must list every queued id exactly once")
        self._items[session_id] = [by_id[input_id] for input_id in order]

    def cancel(self, session_id: str, input_id: str) -> None:
        items = self._items.get(session_id) or []
        kept = [item for item in items if item.input_id != input_id]
        if len(kept) == len(items):
            raise KeyError(f"unknown queued input {input_id!r}")
        if kept:
            self._items[session_id] = kept
        else:
            self._items.pop(session_id, None)

    def clear_session(self, session_id: str) -> None:
        self._items.pop(session_id, None)
