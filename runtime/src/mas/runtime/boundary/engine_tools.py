#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Contracts for engine tools that cross into ctl orchestration."""

from __future__ import annotations

from typing import Any, Protocol


class EngineToolContract(Protocol):
    """Claim and execute one orchestration-level tool call."""

    def claims(self, tool_name: str) -> bool: ...

    def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str: ...


class SubagentContract(Protocol):
    """Spawn a bounded, named subagent template for one task."""

    def is_subagent_tool(self, tool_name: str) -> bool: ...

    def spawn(
        self,
        template_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str: ...