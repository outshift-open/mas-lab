#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Local Tool Provider Plugin."""

import logging
from typing import Any, Dict

from mas.runtime.plugins.plugin_manager import ProviderPlugin
from mas.runtime.registry.tool_provider_registry import ToolProviderRegistry
from mas.runtime.engine.manifest_tool_provider import build_manifest_tool_provider
from pathlib import Path

logger = logging.getLogger(__name__)

class LocalProviderPlugin(ProviderPlugin):
    """
    Plugin that handles 'kind: local' tool definitions.
    """

    def __init__(self, manifest_dir: Path) -> None:
        self._manifest_dir = manifest_dir

    def on_startup(self, registry: ToolProviderRegistry) -> None:
        """
        Optionally register a default local provider if needed.
        For now, we wait for manifests to be loaded.
        """
        pass

    def on_manifest_load(self, manifest_content: Dict[str, Any], registry: ToolProviderRegistry) -> None:
        """
        Intercept 'kind: local' entries in the manifest and register them.
        """
        providers_spec = manifest_content.get("providers", [])
        for spec in providers_spec:
            if spec.get("kind") == "local":
                try:
                    # Create a provider from this specific provider spec
                    # In a real implementation, this might involve more complex
                    # parsing of the 'spec' block.
                    provider = build_manifest_tool_provider(
                        tools_spec=spec.get("tools", []),
                        manifest_dir=self._manifest_dir,
                        # We pass the spec itself as tool_def to build_manifest_tool_provider
                        # if it's designed to handle it, or we adapt it.
                        **spec.get("params", {})
                    )
                    registry.register_provider(provider)
                    logger.info("Registered local provider from manifest: %s", spec.get("name", "unnamed"))
                except Exception as e:
                    logger.error("Failed to register local provider: %s", e, exc_info=True)
