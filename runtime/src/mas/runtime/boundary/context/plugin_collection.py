#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""PluginCollection — lightweight runtime plugin registry for hook dispatch.

This class is the runtime-side implementation of the interface that
``ContextAssemblerPlugin.on_pre_llm_call()`` (library-standard) expects as
``agent.registry``:

    registry.collect_results("collect_context")
    registry.get_plugins_by_type(ContextContract)

It replaces the ad-hoc ``ctx.context_plugins: list[Any]`` field that was used
as a v0.1 bridge and unifies both the collection mechanism and the query
interface in a single object.

Usage in the v0.1 assembly path
---------------------------------
``AutoCtxAssembler.plugin_collection`` holds this object.
``assemble_llm_messages()`` calls
``ctx.plugin_collection.collect_results("collect_context")`` to gather
``ContextPart`` objects from all registered ``ContextContract`` plugins.

Usage with ``ContextAssemblerPlugin`` (target architecture)
--------------------------------------------------------------
When ``ContextAssemblerPlugin.attach_agent(agent)`` is called and the agent
exposes ``agent.registry = ctx.plugin_collection``, the assembler plugin can
call ``registry.collect_results("collect_context")`` in its
``on_pre_llm_call()`` hook — no code change needed in the library plugin.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PluginCollection:
    """Ordered collection of plugin instances with hook dispatch.

    Plugins are stored in registration order.  ``collect_results`` calls
    ``on_{hook_name}()`` on every registered plugin that defines the method,
    flattening list results into a single list.

    This is deliberately minimal: no lifecycle management, no dependency
    injection, no type-based auto-wiring.  Those concerns belong in the full
    L4 plugin registry (future work).
    """

    def __init__(self) -> None:
        self._plugins: list[Any] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, plugin: Any) -> None:
        """Append *plugin* to the collection."""
        self._plugins.append(plugin)

    # ------------------------------------------------------------------
    # Hook dispatch — interface expected by ContextAssemblerPlugin
    # ------------------------------------------------------------------

    def collect_results(self, hook_name: str) -> list[Any]:
        """Call ``on_{hook_name}()`` on every registered plugin; flatten results.

        The method signature ``on_collect_context() -> List[ContextPart]`` is
        the primary use case.  Any iterable result is extended into the output
        list.  ``None`` returns are silently skipped.  Plugin errors are logged
        and isolated — they must not break assembly.
        """
        method = f"on_{hook_name}"
        results: list[Any] = []
        for plugin in self._plugins:
            handler = getattr(plugin, method, None)
            if not callable(handler):
                continue
            try:
                result = handler()
            except Exception as exc:
                logger.warning(
                    "PluginCollection.collect_results(%r): plugin %r raised: %s",
                    hook_name, plugin.__class__.__name__, exc,
                )
                continue
            if result is None:
                continue
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # Type-based query — interface expected by ContextResolver
    # ------------------------------------------------------------------

    def get_plugins_by_type(self, contract_type: type) -> list[Any]:
        """Return all registered plugins that are instances of *contract_type*."""
        return [p for p in self._plugins if isinstance(p, contract_type)]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._plugins)

    def __bool__(self) -> bool:
        return bool(self._plugins)

    def __repr__(self) -> str:
        names = [p.__class__.__name__ for p in self._plugins]
        return f"PluginCollection({names})"
