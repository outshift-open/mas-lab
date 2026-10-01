#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Session-scoped spawn budgets and stable subagent identities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpawnLedger:
    """Enforce session-wide spawn count and recursion depth at the caller boundary."""

    max_depth: int = 3
    max_spawns: int | None = 8
    _depth: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _spawn_count: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _sequence: dict[tuple[str, str], int] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.max_depth, int) or isinstance(self.max_depth, bool) or self.max_depth < 1:
            raise ValueError("max_depth must be an integer >= 1")
        if self.max_spawns is not None and (
            not isinstance(self.max_spawns, int)
            or isinstance(self.max_spawns, bool)
            or self.max_spawns < 1
        ):
            raise ValueError("max_spawns must be None or an integer >= 1")

    def allow_spawn(self, session_id: str, parent_agent_id: str = "") -> bool:
        """Check both ceilings without mutating counters."""
        if not self.allows_child_depth(self._depth.get(session_id, 0)):
            return False
        return self.max_spawns is None or self._spawn_count.get(session_id, 0) < self.max_spawns

    def allows_child_depth(self, parent_depth: Any) -> bool:
        """Return whether one child under a typed, non-negative parent depth fits K."""
        return (
            isinstance(parent_depth, int)
            and not isinstance(parent_depth, bool)
            and parent_depth >= 0
            and parent_depth + 1 <= self.max_depth
        )

    def mint_agent_id(self, parent_agent_id: str, template_id: str) -> str:
        """Return a deterministic, unique child ID for this parent/template pair."""
        key = (parent_agent_id, template_id)
        sequence = self._sequence.get(key, 0) + 1
        self._sequence[key] = sequence
        return f"{parent_agent_id}.{template_id}.{sequence}"

    def enter(self, session_id: str) -> None:
        """Account for a spawn immediately before its synchronous nested turn."""
        self._depth[session_id] = self._depth.get(session_id, 0) + 1
        self._spawn_count[session_id] = self._spawn_count.get(session_id, 0) + 1

    def exit(self, session_id: str) -> None:
        """Release one level after the nested turn, including failures."""
        depth = self._depth.get(session_id, 0)
        if depth <= 0:
            raise RuntimeError(f"spawn ledger underflow for session {session_id!r}")
        self._depth[session_id] = depth - 1

    def spawn_count(self, session_id: str) -> int:
        """Total children started in one session."""
        return self._spawn_count.get(session_id, 0)

    def current_depth(self, session_id: str) -> int:
        """Current synchronous recursion depth for one session."""
        return self._depth.get(session_id, 0)