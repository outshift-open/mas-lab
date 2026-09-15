#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Protocol for pluggable tool providers (local and MCP)."""

from typing import Dict, Any, List, Protocol, runtime_checkable
import logging

logger = logging.getLogger(__name__)

@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for tool providers in the MAS runtime."""
    
    def has_tools(self) -> bool:
        ...

    def list_tools(self, *, ctx: Any = None) -> List[Dict[str, Any]]:
        """Return a list of tool specifications."""
        ...

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        ctx: Any = None,
        user: str = "",
    ) -> Any:
        """Execute a tool by name."""
        ...
