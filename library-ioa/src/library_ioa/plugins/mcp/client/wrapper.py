#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, Dict, List, TypeVar

from library_ioa.plugins.mcp.client import MCPClient

_T = TypeVar("_T")


def run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run an async MCP operation from sync plugin code.

    Uses ``asyncio.run`` when no loop is running. If the caller already has a
    loop, runs the coroutine on a private loop in a worker thread so the
    ephemeral MCP transport never spans loops.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    holder: dict[str, Any] = {}

    def _worker() -> None:
        try:
            holder["result"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller thread
            holder["error"] = exc

    thread = threading.Thread(target=_worker, name="mcp-run-sync", daemon=True)
    thread.start()
    thread.join()
    if "error" in holder:
        raise holder["error"]
    return holder["result"]


class MCPClientWrapper:
    """Bridge the async MCP client to the synchronous runtime plugin API."""

    def __init__(self, client: MCPClient):
        self._client = client

    async def list_tools(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return await self._client.list_tools(**kwargs)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], **options: Any) -> Dict[str, Any]:
        return await self._client.call_tool(tool_name, arguments, **options)

    def invalidate_list_cache(self) -> None:
        self._client.invalidate_list_cache()

    async def connect(self) -> None:
        await self._client.connect()

    async def disconnect(self) -> None:
        await self._client.disconnect()
