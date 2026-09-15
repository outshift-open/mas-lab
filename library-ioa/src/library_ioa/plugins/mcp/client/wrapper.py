from __future__ import annotations

from typing import Any, Dict, List

from library_ioa.plugins.mcp.client import MCPClient


class MCPClientWrapper:
    """Bridge the async MCP client to the synchronous runtime API."""

    def __init__(self, client: MCPClient):
        self._client = client

    async def list_tools(self) -> List[Dict[str, Any]]:
        return await self._client.list_tools()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.call_tool(tool_name, arguments)

    async def connect(self) -> None:
        await self._client.connect()

    async def disconnect(self) -> None:
        await self._client.disconnect()
