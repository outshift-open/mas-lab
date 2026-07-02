#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation plugin contract — ``delegate_to_*`` tool execution over CommBus."""

from __future__ import annotations

from typing import Any, Protocol


class DelegationContract(Protocol):
    """Execute peer delegation tools surfaced by MAS ``workflow.delegates_to``."""

    def delegate(self, target_agent_id: str, task: str) -> str: ...

    def call_delegate_tool(self, tool_name: str, arguments: dict[str, Any] | None) -> str: ...

    def is_delegate_tool(self, tool_name: str) -> bool: ...
