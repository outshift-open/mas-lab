#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Default delegation plugin — ``delegate_to_*`` over materialized CommBus."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

RunTurnFn = Callable[[str, str], str]


class LlmDelegator:
    """``DelegationContract`` implementation via ctl bus-aware ``run_turn``."""

    def __init__(
        self,
        *,
        run_turn: RunTurnFn,
    ) -> None:
        self._run_turn = run_turn
        self._completed_peers: dict[tuple[str, str], str] = {}

    def reset_session(self) -> None:
        """Clear per-session delegate cache (new user incident)."""
        self._completed_peers.clear()

    def is_delegate_tool(self, tool_name: str) -> bool:
        from mas.runtime.boundary.delegation.policy import DELEGATE_TOOL_PREFIX

        return tool_name.startswith(DELEGATE_TOOL_PREFIX) and len(tool_name) > len(
            DELEGATE_TOOL_PREFIX
        )

    def delegate(self, target_agent_id: str, task: str) -> str:
        if not target_agent_id:
            return "[delegation] missing target agent id"
        task_key = task.strip()
        cache_key = (target_agent_id, task_key)
        if cache_key in self._completed_peers:
            return (
                f"[delegation] {target_agent_id!r} already consulted this session for "
                "the same task — use the findings below; call the next specialist instead.\n\n"
                f"{self._completed_peers[cache_key]}"
            )
        try:
            result = self._run_turn(target_agent_id, task_key)
        except KeyError:
            return f"[delegation] agent {target_agent_id!r} not available on bus"
        except RuntimeError as exc:
            return f"[delegation] agent {target_agent_id!r} failed: {exc}"
        self._completed_peers[cache_key] = result
        return result

    def call_delegate_tool(self, tool_name: str, arguments: dict[str, Any] | None) -> str:
        from mas.runtime.boundary.delegation.policy import parse_delegate_tool_name

        target = parse_delegate_tool_name(tool_name)
        if not target:
            return f"[delegation] not a delegate tool: {tool_name!r}"
        task = str((arguments or {}).get("task") or "").strip()
        if not task:
            return f"[delegation] missing task for {target!r}"
        return self.delegate(target, task)
