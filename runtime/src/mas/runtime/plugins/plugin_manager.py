#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Lifecycle hooks for tool-provider plugins."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

@runtime_checkable
class ProviderPlugin(Protocol):
    """Plugin interface for registering tool providers via hooks."""

    def on_startup(self, registry: Any) -> None:
        """Called when the runtime starts. Use to register default providers."""
        ...

    def on_manifest_load(self, manifest_content: Dict[str, Any], registry: Any) -> None:
        """Called when a manifest is loaded. Use to intercept provider definitions."""
        ...

class PluginManager:
    """Manages lifecycle hooks for runtime plugins."""

    def __init__(self) -> None:
        self._plugins: List[ProviderPlugin] = []

    def register_plugin(self, plugin: ProviderPlugin) -> None:
        """Register a new plugin."""
        self._plugins.append(plugin)
        logger.debug("Registered plugin: %s", plugin.__class__.__name__)

    def trigger_on_startup(self, registry: Any) -> None:
        """Trigger the on_startup hook for all plugins."""
        for plugin in self._plugins:
            try:
                plugin.on_startup(registry)
            except Exception as e:
                logger.error("Error in plugin %s during on_startup: %s", plugin.__class__.__name__, e, exc_info=True)

    def trigger_on_manifest_load(self, manifest_content: Dict[str, Any], registry: Any) -> None:
        """Trigger the on_manifest_load hook for all plugins."""
        for plugin in self._plugins:
            try:
                plugin.on_manifest_load(manifest_content, registry)
            except Exception as e:
                logger.error("Error in plugin %s during on_manifest_load: %s", plugin.__class__.__name__, e, exc_info=True)
