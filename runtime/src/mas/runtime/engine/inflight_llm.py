#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-flight LLM tasks — hard interrupt of ``ainvoke`` only."""

from __future__ import annotations

import asyncio
from typing import Any

_tasks: dict[str, asyncio.Task[Any]] = {}


def register(session_id: str, task: asyncio.Task[Any]) -> None:
    if session_id:
        _tasks[session_id] = task


def clear(session_id: str) -> None:
    _tasks.pop(session_id, None)


def cancel(session_id: str) -> bool:
    """Cancel the in-flight LLM ``ainvoke``. Tools are not cancellable here."""
    task = _tasks.get(session_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def has_inflight(session_id: str) -> bool:
    task = _tasks.get(session_id)
    return task is not None and not task.done()
