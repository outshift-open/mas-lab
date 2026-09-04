#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Signals raised by system tools to trigger runtime actions."""

from __future__ import annotations

from typing import Any

from mas.runtime.schema.hitl import HitlQuestionType


class RequestHitlSignal(Exception):
    """Signal raised by request_human_input tool to trigger HITL emission.

    This is **not an error** — it's a control flow signal that tells the
    tool execution layer to:
    1. Emit an EmitHitlRequest to the kernel
    2. Pause the agent's turn
    3. Wait for external HITL resolution
    4. Resume the turn with the user's response as the tool result

    The tool dispatch layer (execute_engine_tool) will catch this and handle it.
    """

    def __init__(
        self,
        *,
        question: str,
        question_type: HitlQuestionType,
        choices: list[str] | None = None,
        context_data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> None:
        self.question = question
        self.question_type = question_type
        self.choices = choices or []
        self.context_data = context_data or {}
        self.timeout = timeout
        super().__init__(f"HITL request: {question}")


class InformUserSignal(Exception):
    """Signal raised by inform_user for a non-blocking status update.

    This is a HITL-adjacent control message: it emits a side-channel update to the
    user without waiting for a return channel or modifying runtime state.
    """

    def __init__(
        self,
        *,
        message: str,
        user_name: str = "",
        involved_agents: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.user_name = user_name
        self.involved_agents = involved_agents or []
        self.metadata = metadata or {}
        super().__init__(f"User update: {message}")
