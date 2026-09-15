from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)


class MCPClient:
    """Manage a real MCP client session backed by the official SDK."""

    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        url: str | None = None,
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.url = url
        self._session: ClientSession | None = None
        self._stdio_cm = None
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return
        if self.url:
            self._http_cm = streamable_http_client(self.url)
            self._read_stream, self._write_stream = await self._http_cm.__aenter__()
            self._session = ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()
            await self._session.initialize()
            self._connected = True
            return
        if not self.command:
            raise ValueError("MCP client requires a command to start the server")

        params = StdioServerParameters(command=self.command, args=self.args, env=self.env, cwd=self.cwd)
        self._stdio_cm = stdio_client(params)
        self._read_stream, self._write_stream = await self._stdio_cm.__aenter__()
        self._session = ClientSession(self._read_stream, self._write_stream)
        await self._session.__aenter__()
        await self._session.initialize()
        self._connected = True

    async def disconnect(self) -> None:
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(None, None, None)
            self._stdio_cm = None
        if hasattr(self, "_http_cm") and self._http_cm is not None:
            await self._http_cm.__aexit__(None, None, None)
            self._http_cm = None
        self._connected = False

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.connect()
        assert self._session is not None
        result = await self._session.list_tools()
        return [tool.model_dump(mode="json") for tool in result.tools]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self.connect()
        assert self._session is not None
        result = await self._session.call_tool(tool_name, arguments)
        if result.is_error:
            raise RuntimeError(f"MCP tool {tool_name} reported an error: {result}")
        return {
            "content": [item.model_dump(mode="json") for item in result.content],
            "structured_content": result.structured_content,
            "is_error": result.is_error,
        }
