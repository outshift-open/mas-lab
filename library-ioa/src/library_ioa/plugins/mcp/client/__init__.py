#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.types import PaginatedRequestParams

logger = logging.getLogger(__name__)

_HTTP_TRANSPORTS = {"streamable-http", "http"}
_SSE_TRANSPORTS = {"sse"}


def _streams_from_transport(transport: Any) -> tuple[Any, Any]:
    """streamable_http_client / stdio_client / sse_client yield (read, write) or (read, write, extra)."""
    if isinstance(transport, (tuple, list)) and len(transport) >= 2:
        return transport[0], transport[1]
    raise TypeError(f"unexpected MCP transport yield: {type(transport)!r}")


class MCPClient:
    """MCP client session backed by the official SDK.

    Each list/call opens and closes the transport in the same task. The
    provider drives the client through ``run_sync`` (``asyncio.run`` when no
    loop is running, otherwise a private loop in a worker thread). Holding
    the transport across event loops raises GeneratorExit / cancel-scope
    RuntimeError on close.

    ``cache_ttl_ms`` / ``cache_scope`` control the client's ``tools/list``
    cache. Omit TTL to keep the list until ``invalidate_list_cache``. ``0``
    disables the cache. ``private`` keys the cache by user.
    """

    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        transport: str | None = None,
        follow_pagination: bool = True,
        cache_ttl_ms: int | None = None,
        cache_scope: str | None = None,
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.url = url
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.follow_pagination = follow_pagination
        self.cache_ttl_ms = cache_ttl_ms
        self.cache_scope = cache_scope if cache_scope in {"public", "private"} else None
        self._list_cache: dict[str, tuple[float, list[dict[str, Any]], int | None]] = {}
        if transport:
            self.transport = transport
        elif url:
            self.transport = "streamable-http"
        else:
            self.transport = "stdio"

    def invalidate_list_cache(self) -> None:
        self._list_cache.clear()

    def _cache_key(self, user: str) -> str:
        if self.cache_scope == "private":
            return user
        return ""

    def _cached_list(self, user: str) -> list[dict[str, Any]] | None:
        if self.cache_ttl_ms == 0:
            return None
        packed = self._list_cache.get(self._cache_key(user))
        if packed is None:
            return None
        stored_at, payload, ttl_ms = packed
        if ttl_ms is None:
            return payload
        age_ms = (time.monotonic() - stored_at) * 1000
        if age_ms >= ttl_ms:
            return None
        return payload

    def _store_list(self, user: str, payload: list[dict[str, Any]], *, server_ttl: int | None = None) -> None:
        if self.cache_ttl_ms == 0:
            return
        ttl = self.cache_ttl_ms if self.cache_ttl_ms is not None else server_ttl
        self._list_cache[self._cache_key(user)] = (time.monotonic(), payload, ttl)

    @asynccontextmanager
    async def _ephemeral_session(self) -> AsyncIterator[ClientSession]:
        if self.transport in _SSE_TRANSPORTS:
            if not self.url:
                raise ValueError("MCP SSE client requires a url")
            sse_kw: dict[str, Any] = {}
            if self.headers:
                sse_kw["headers"] = self.headers
            async with sse_client(self.url, **sse_kw) as transport:
                read_stream, write_stream = _streams_from_transport(transport)
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return

        if self.transport in _HTTP_TRANSPORTS or (self.url and self.transport != "stdio"):
            if not self.url:
                raise ValueError("MCP HTTP client requires a url")
            # Connection timeout stays on the SDK client (30s / 300s read).
            # spec timeout is call_tool read_timeout_seconds, not the HTTP budget.
            if self.headers:
                async with create_mcp_http_client(headers=self.headers) as http_client:
                    async with streamable_http_client(self.url, http_client=http_client) as transport:
                        read_stream, write_stream = _streams_from_transport(transport)
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            yield session
                return
            async with streamable_http_client(self.url) as transport:
                read_stream, write_stream = _streams_from_transport(transport)
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return

        if not self.command:
            raise ValueError("MCP client requires a command to start the server")

        params = StdioServerParameters(command=self.command, args=self.args, env=self.env or None, cwd=self.cwd)
        async with stdio_client(params) as transport:
            read_stream, write_stream = _streams_from_transport(transport)
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def connect(self) -> None:
        """No-op. Sessions are opened per list/call so they never outlive the loop."""
        return None

    async def disconnect(self) -> None:
        """No-op. See ``connect``."""
        return None

    async def list_tools(self, *, user: str = "") -> list[dict[str, Any]]:
        """Return the advertised set, following MCP ``nextCursor`` when enabled."""
        cached = self._cached_list(user)
        if cached is not None:
            return cached
        async with self._ephemeral_session() as session:
            collected: list[dict[str, Any]] = []
            cursor: str | None = None
            seen: set[str] = set()
            server_ttl: int | None = None
            while True:
                params = PaginatedRequestParams(cursor=cursor) if cursor else None
                result = await session.list_tools(params=params)
                collected.extend(tool.model_dump(mode="json", by_alias=True) for tool in result.tools)
                page_ttl = getattr(result, "ttl_ms", None)
                if page_ttl is not None:
                    page_ttl_i = int(page_ttl)
                    server_ttl = page_ttl_i if server_ttl is None else min(server_ttl, page_ttl_i)
                if not self.follow_pagination:
                    break
                cursor = getattr(result, "next_cursor", None)
                if not cursor or cursor in seen:
                    break
                seen.add(cursor)
            self._store_list(user, collected, server_ttl=server_ttl)
            return collected

    async def call_tool(self, tool_name: str, arguments: dict[str, Any], **options: Any) -> dict[str, Any]:
        call_kwargs: dict[str, Any] = {}
        timeout = options.get("timeout_seconds", self.timeout)
        if timeout is not None:
            call_kwargs["read_timeout_seconds"] = timeout
        for src, dest in (
            ("progress_callback", "progress_callback"),
            ("meta", "meta"),
            ("input_responses", "input_responses"),
            ("request_state", "request_state"),
            ("allow_input_required", "allow_input_required"),
            ("allow_claimed", "allow_claimed"),
        ):
            if src in options and options[src] is not None:
                call_kwargs[dest] = options[src]
        async with self._ephemeral_session() as session:
            result = await session.call_tool(tool_name, arguments, **call_kwargs)
            return result.model_dump(mode="json", by_alias=True)
