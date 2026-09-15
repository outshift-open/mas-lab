#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCP Tool Provider - Integrates MCP servers into the MAS runtime."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from mas.runtime.registry.provider_protocol import ToolProvider
from library_ioa.plugins.mcp.client.wrapper import MCPClientWrapper

logger = logging.getLogger(__name__)


class MCPToolProvider(ToolProvider):
    """A ToolProvider that delegates tool calls to an MCP client."""

    def __init__(self, client_wrapper: MCPClientWrapper) -> None:
        self._client = client_wrapper
        self._tools_cache: Optional[List[Dict[str, Any]]] = None

    @staticmethod
    def _as_tool_specs(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            if "tools" in payload and isinstance(payload["tools"], list):
                return [dict(item) for item in payload["tools"]]
            if "result" in payload and isinstance(payload["result"], list):
                return [dict(item) for item in payload["result"]]
            return []
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        return []

    @staticmethod
    def _as_result_payload(payload: Any) -> Any:
        if isinstance(payload, dict):
            if "content" in payload:
                content = payload["content"]
                if isinstance(content, list):
                    text_items = [part.get("text") for part in content if isinstance(part, dict) and "text" in part]
                    if text_items:
                        return {"result": "".join(str(item) for item in text_items)}
                return {"result": payload.get("content")}
            return payload
        if isinstance(payload, list):
            return {"result": payload}
        return {"result": payload}

    def has_tools(self) -> bool:
        return self._client is not None

    def list_tools(self, *, ctx: Any = None) -> List[Dict[str, Any]]:
        if self._tools_cache is not None:
            return self._tools_cache

        try:
            tools = asyncio.run(self._client.list_tools())
            self._tools_cache = self._as_tool_specs(tools)
            return self._tools_cache
        except Exception as exc:  # pragma: no cover - transport failures logged
            logger.error("Failed to list tools from MCP client: %s", exc, exc_info=True)
            return []

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        ctx: Any = None,
        user: str = "",
    ) -> Any:
        try:
            result = asyncio.run(self._client.call_tool(tool_name, arguments))
            return self._as_result_payload(result)
        except Exception as exc:
            logger.error("Error calling MCP tool %s: %s", tool_name, exc, exc_info=True)
            raise
