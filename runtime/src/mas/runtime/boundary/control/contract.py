#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ControlContract — pause, steer, list, and walk snapshots.

Plugin code, an LLM tool advertisement, and an admin CLI all call the
same methods. The tool is never a second implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

Surface = Literal["plugin", "llm", "admin"]


class SessionPaused(RuntimeError):
    """The session is paused; user turns are refused until ``resume``."""

    def __init__(self, session_id: str, *, reason: str = "") -> None:
        self.session_id = session_id
        self.reason = reason
        extra = f": {reason}" if reason else ""
        super().__init__(f"session {session_id!r} is paused{extra}")


class ControlDenied(RuntimeError):
    """A control verb was refused; the refusal is still traced."""

    def __init__(self, method: str, session_id: str, *, reason: str) -> None:
        self.method = method
        self.session_id = session_id
        self.reason = reason
        super().__init__(f"{method} denied for session {session_id!r}: {reason}")


@dataclass(frozen=True)
class ControlCapability:
    """Least-privilege token for one caller of ``ControlContract``."""

    actor: str
    surface: Surface
    session_ids: frozenset[str] | None = None
    methods: frozenset[str] | None = None

    def allows(self, method: str, session_id: str) -> bool:
        if self.session_ids is not None and session_id not in self.session_ids:
            return False
        if self.methods is not None and method not in self.methods:
            return False
        return True


@dataclass(frozen=True)
class ControlEvent:
    """One governed control action, reconstructable without a private index."""

    kind: str
    session_id: str
    actor: str
    surface: Surface
    method: str
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    denied: bool = False
    taken_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class QueuedInputView:
    input_id: str
    text: str
    source: str
    priority: int = 0


@dataclass(frozen=True)
class SessionSnapshotView:
    session_id: str
    status: str
    turn: int
    live_snapshot_id: str | None
    cursor_snapshot_id: str | None
    spec_revision: int | None = None


class ControlContract(Protocol):
    """Capability-scoped control plane. Callers pass ``session_id``, not objects."""

    def pause(self, session_id: str, *, reason: str) -> None: ...
    def resume(self, session_id: str) -> None: ...
    def steer(self, session_id: str, *, text: str, mode: Literal["inject_now", "enqueue"] = "inject_now") -> None: ...
    def discard_last(self, session_id: str) -> str: ...
    def inspect(self, session_id: str) -> SessionSnapshotView: ...
    def list_checkpoints(self, session_id: str) -> list[Any]: ...
    def navigate(self, session_id: str, *, to: str, reason: str) -> Any: ...
    def enqueue_input(self, session_id: str, *, text: str, source: str, priority: int = 0) -> str: ...
    def peek_queue(self, session_id: str) -> list[QueuedInputView]: ...
    def reorder_queue(self, session_id: str, order: list[str]) -> None: ...
    def cancel_queued(self, session_id: str, input_id: str) -> None: ...
    def cancel_inflight(self, session_id: str) -> bool: ...
    def fork_investigation(self, session_id: str) -> str: ...
    def disable_tool(self, session_id: str, *, name: str, reason: str) -> int: ...
