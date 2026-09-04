#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill session state — per-session tracking of activated skills.

Implements agentskills.io Step 5 §Deduplicate activations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActivatedSkill:
    """Record of a skill that has been loaded during the current session."""

    name: str
    turn: int = 0         # conversation turn index when activated (informational)
    notices: int = 0      # how many times re-activation was attempted (for telemetry)


class SkillSessionState:
    """Per-session tracker for activated skills.

    Thread-safety is not required: a single agent session is processed
    sequentially.
    """

    def __init__(self) -> None:
        self._activated: dict[str, ActivatedSkill] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def mark_activated(self, name: str, turn: int = 0) -> ActivatedSkill:
        """Record *name* as activated.

        Idempotent — returns existing record on repeat.
        """
        if name not in self._activated:
            self._activated[name] = ActivatedSkill(name=name, turn=turn)
        return self._activated[name]

    def note_reactivation_attempt(self, name: str) -> None:
        """Increment the re-activation counter for *name* (for metrics/telemetry)."""
        if name in self._activated:
            self._activated[name].notices += 1

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_activated(self, name: str) -> bool:
        return name in self._activated

    def get(self, name: str) -> ActivatedSkill | None:
        return self._activated.get(name)

    def activated_names(self) -> list[str]:
        return list(self._activated)

    def __len__(self) -> int:
        return len(self._activated)

    def __bool__(self) -> bool:
        return bool(self._activated)

    def __repr__(self) -> str:
        return f"SkillSessionState(activated={self.activated_names()})"
