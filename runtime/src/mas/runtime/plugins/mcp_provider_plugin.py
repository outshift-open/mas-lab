#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCP Tool Provider Plugin."""

import logging
from typing import Any, Dict, Optional, Type

from mas.runtime.engine.mcp_tool_provider import MCPToolProvider
from mas.runtime.plugins.plugin_manager import ProviderPlugin
from mas.runtime.registry.tool_provider_registry import ToolProviderRegistry
from library_ioa.plugins.mcp.client import MCPClient
from library_ioa.plugins.mcp.client.wrapper import MCPClientWrapper

logger = logging.getLogger(__name__)


class MCPClientFactory:
    """Build a lightweight MCP client from a manifest provider spec."""

    def __init__(
        self,
        *,
        transport: str = "stdio",
        command: Optional[str] = None,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        url: Optional[str] = None,
        **_: Any,
    ) -> None:
        self.transport = transport
        self.command = command
        self.args = list(args or [])
        self.env = env or {}
        self.cwd = cwd
        self.url = url

    def create_client(self) -> MCPClientWrapper:
        if self.url and self.transport in {"streamable-http", "sse", "http"}:
            return MCPClientWrapper(MCPClient(url=self.url))
        if self.command:
            return MCPClientWrapper(
                MCPClient(command=self.command, args=self.args, env=self.env, cwd=self.cwd)
            )
        raise ValueError("MCP provider requires either command or url metadata")


class MCPProviderPlugin(ProviderPlugin):
    """Plugin that handles 'kind: mcp' tool definitions."""

    def __init__(self, factory_cls: Optional[Type[MCPClientFactory]] = None) -> None:
        self._factory_cls = factory_cls or MCPClientFactory

    def on_startup(self, registry: ToolProviderRegistry) -> None:
        return None

    def on_manifest_load(self, manifest_content: Dict[str, Any], registry: ToolProviderRegistry) -> None:
        """Intercept 'kind: mcp' entries in the manifest and register them."""
        providers_spec = manifest_content.get("providers", [])
        for spec in providers_spec:
            if spec.get("kind") != "mcp":
                continue
            try:
                factory = self._factory_cls(
                    transport=spec.get("transport", "stdio"),
                    command=spec.get("command"),
                    args=spec.get("args"),
                    env=spec.get("env"),
                    cwd=spec.get("cwd"),
                    url=spec.get("url") or spec.get("endpoint"),
                    **spec.get("params", {}),
                )
                provider = MCPToolProvider(factory.create_client())
                registry.register_provider(provider)
                logger.info(
                    "Registered MCP provider from manifest: %s (%s)",
                    spec.get("name", "unnamed"),
                    spec.get("transport", "stdio"),
                )
            except Exception as exc:  # pragma: no cover - logging path
                logger.error("Failed to register MCP provider: %s", exc, exc_info=True)
