#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-flight LLM tasks — hard interrupt of ``ainvoke`` only.

A2A ``tasks/cancel`` maps to :func:`cancel` (drop the remainder, no follow-up).
:func:`request_preempt` is control-protocol ``steer``: keep streamed tokens
and continue the same generation. :func:`request_replace` discards the
partial and starts a new turn. A2A has no steer RPC; additional
``message/send`` traffic is queued, not preempted.
"""

from __future__ import annotations

import asyncio
from typing import Any

_tasks: dict[str, asyncio.Task[Any]] = {}
_partials: dict[str, str] = {}
_preempts: dict[str, str] = {}
_replaces: dict[str, str] = {}


def register(session_id: str, task: asyncio.Task[Any]) -> None:
    if session_id:
        _tasks[session_id] = task


def clear(session_id: str) -> None:
    _tasks.pop(session_id, None)
    if session_id not in _preempts and session_id not in _replaces:
        _partials.pop(session_id, None)


def append_partial(session_id: str, text: str) -> None:
    if not session_id or not text:
        return
    _partials[session_id] = _partials.get(session_id, "") + text


def take_partial(session_id: str) -> str:
    return _partials.pop(session_id, "")


def peek_preempt(session_id: str) -> str | None:
    return _preempts.get(session_id)


def pop_preempt(session_id: str) -> str | None:
    return _preempts.pop(session_id, None)


def peek_replace(session_id: str) -> str | None:
    return _replaces.get(session_id)


def pop_replace(session_id: str) -> str | None:
    return _replaces.pop(session_id, None)


def request_preempt(session_id: str, text: str) -> bool:
    """Keep streamed tokens and stop the rest of this decode (steer)."""
    if session_id:
        _preempts[session_id] = text
        _replaces.pop(session_id, None)
    return cancel(session_id)


def request_replace(session_id: str, text: str) -> bool:
    """Discard streamed tokens and stop this decode for a replacement turn."""
    if session_id:
        _replaces[session_id] = text
        _preempts.pop(session_id, None)
        _partials.pop(session_id, None)
    return cancel(session_id)


def peek_amend(session_id: str) -> str | None:
    """Alias of :func:`peek_preempt`."""
    return peek_preempt(session_id)


def pop_amend(session_id: str) -> str | None:
    """Alias of :func:`pop_preempt`."""
    return pop_preempt(session_id)


def request_amend(session_id: str, text: str) -> bool:
    """Alias of :func:`request_preempt`."""
    return request_preempt(session_id, text)


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
