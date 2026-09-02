#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Default delegation plugin — ``delegate_to_*`` over materialized CommBus."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

RunTurnFn = Callable[[str, str, int, str, str], str]


class LlmDelegator:
    """``DelegationContract`` implementation via ctl bus-aware ``run_turn``."""

    def __init__(
        self,
        *,
        run_turn: RunTurnFn,
    ) -> None:
        self._run_turn = run_turn
        # Compatibility cache retained for reset/session lifecycle hooks and tests.
        # Delegations are intentionally executed fresh each round; this cache is only
        # a bookkeeping record and must never suppress a new call.
        self._completed_peers: dict[tuple[str, str, str], str] = {}

    def reset_session(self) -> None:
        """Clear per-session delegate cache (new user incident)."""
        self._completed_peers.clear()

    def is_delegate_tool(self, tool_name: str) -> bool:
        from mas.runtime.boundary.delegation.policy import DELEGATE_TOOL_PREFIX

        return tool_name.startswith(DELEGATE_TOOL_PREFIX) and len(tool_name) > len(
            DELEGATE_TOOL_PREFIX
        )

    def delegate(
        self,
        target_agent_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
        context_id: str = "",
    ) -> str:
        if not target_agent_id:
            return "[delegation] missing target agent id"
        task_key = task.strip()
        try:
            result = self._run_turn(
                target_agent_id, task_key, correlation_id, caller_call_id, context_id
            )
        except KeyError:
            return f"[delegation] agent {target_agent_id!r} not available on bus"
        except RuntimeError as exc:
            return f"[delegation] agent {target_agent_id!r} failed: {exc}"

        # Keep the completion cache for compatibility/reset hooks without blocking
        # future delegations. Fresh execution remains the source of truth.
        self._completed_peers[(target_agent_id, task_key, caller_call_id)] = result
        return result

    def call_delegate_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str:
        from mas.runtime.boundary.delegation.policy import parse_delegate_tool_name

        target = parse_delegate_tool_name(tool_name)
        if not target:
            return f"[delegation] not a delegate tool: {tool_name!r}"
        task = str((arguments or {}).get("task") or "").strip()
        if not task:
            return f"[delegation] missing task for {target!r}"
        context_id = str((arguments or {}).get("context_id") or "").strip()
        return self.delegate(
            target,
            task,
            correlation_id=correlation_id,
            caller_call_id=caller_call_id,
            context_id=context_id,
        )
