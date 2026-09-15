#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tool-provider registry — dispatch list/call across MCP, local, and overlay providers."""

from typing import Dict, Any, List, Optional
import logging
from mas.runtime.registry.provider_protocol import ToolProvider

logger = logging.getLogger(__name__)

class ToolProviderRegistry:
    """Registry for managing multiple ToolProviders."""

    def __init__(self) -> None:
        self._providers: List[ToolProvider] = []

    def register_provider(self, provider: ToolProvider) -> None:
        """Register a new tool provider."""
        if not isinstance(provider, ToolProvider):
            raise TypeError(f"Provider must implement ToolProvider protocol, got {type(provider)}")
        self._providers.append(provider)
        logger.debug("Registered tool provider: %s", provider.__class__.__name__)

    def unregister_provider(self, provider: ToolProvider) -> None:
        """Unregister a tool provider."""
        if provider in self._providers:
            self._providers.remove(provider)
            logger.debug("Unregistered tool provider: %s", provider.__class__.__name__)

    def has_tools(self) -> bool:
        """Check if any registered provider has tools."""
        return any(p.has_tools() for p in self._providers)

    def list_tools(self, *, ctx: Any = None) -> List[Dict[str, Any]]:
        """Aggregate tools from all registered providers."""
        all_tools: List[Dict[str, Any]] = []
        for provider in self._providers:
            try:
                tools = provider.list_tools(ctx=ctx)
                if tools:
                    all_tools.extend(tools)
            except Exception as e:
                logger.error("Error listing tools from provider %s: %s", provider.__class__.__name__, e, exc_info=True)
        return all_tools

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        ctx: Any = None,
        user: str = "",
    ) -> Any:
        """Dispatch a tool call to the appropriate provider."""
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                result = provider.call_tool(tool_name, arguments, ctx=ctx, user=user)
                if result is not None:
                    return result
            except Exception as exc:
                last_error = exc
                logger.error(
                    "Error calling tool %s on provider %s: %s",
                    tool_name,
                    provider.__class__.__name__,
                    exc,
                    exc_info=True,
                )
                continue

        if last_error is not None:
            raise last_error
        return None
