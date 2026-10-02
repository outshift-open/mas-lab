#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HITLContract / UserIOContract protocols — implementations are library plugins."""

from __future__ import annotations

from typing import Any, Protocol


class HITLContract(Protocol):
    """Ask a human a question and get their answer back, resuming the agent."""

    def request_approval(
        self,
        *,
        question: str,
        session_id: str,
        requesting_user_id: str,
        agent_id: str,
        correlation_id: int,
        question_type: str,
        choices: list[str],
        context_data: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return at least {"choice": <str>}; may also include "steering"."""
        ...


class UserIOContract(Protocol):
    """Send a non-blocking progress update to whoever is watching the session."""

    def send_progress_update(
        self,
        *,
        message: str,
        session_id: str,
        agent_id: str,
        correlation_id: int,
        requesting_user_id: str,
        involved_agents: list[str],
        metadata: dict[str, Any],
    ) -> Any:
        """Return value is an opaque receipt."""
        ...


__all__ = ["HITLContract", "UserIOContract"]
