#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Framework adapter registry — LangGraph etc. wrap kernel, not replace it."""

from __future__ import annotations

from typing import Protocol

from mas.ctl.compose.models import EffectiveBindManifest, FrameworkAdapterId
from mas.runtime.driver.instance import RuntimeInstance


class FrameworkAdapter(Protocol):
    adapter_id: FrameworkAdapterId

    def wrap(self, instance: RuntimeInstance, bind: EffectiveBindManifest, agent_id: str) -> object:
        """Return runnable handle (native returns instance unchanged)."""


class NativeFrameworkAdapter:
    adapter_id: FrameworkAdapterId = "native"

    def wrap(
        self, instance: RuntimeInstance, bind: EffectiveBindManifest, agent_id: str
    ) -> RuntimeInstance:
        return instance


class LangGraphFrameworkAdapter:
    """LangGraph wraps native RuntimeInstance when langgraph is installed."""

    adapter_id: FrameworkAdapterId = "langgraph"

    def wrap(
        self, instance: RuntimeInstance, bind: EffectiveBindManifest, agent_id: str
    ) -> object:
        from mas.ctl.compose.adapters.langgraph import LangGraphFrameworkAdapter as _Impl

        return _Impl().wrap(instance, bind, agent_id)


_ADAPTERS: dict[str, FrameworkAdapter] = {
}

_CATALOG_REGISTERED = False


def _register_from_catalog() -> None:
    global _CATALOG_REGISTERED
    if _CATALOG_REGISTERED:
        return
    from mas.ctl.registry.catalog import get_framework, import_class, list_framework_ids

    for framework_id in list_framework_ids():
        if framework_id in _ADAPTERS:
            continue
        entry = get_framework(framework_id)
        if entry.module:
            _ADAPTERS[framework_id] = import_class(entry.module)()
    _CATALOG_REGISTERED = True


def list_registered_adapters() -> list[str]:
    _register_from_catalog()
    return sorted(_ADAPTERS.keys())


def get_framework_adapter(adapter_id: FrameworkAdapterId) -> FrameworkAdapter:
    _register_from_catalog()
    if adapter_id in _ADAPTERS:
        return _ADAPTERS[adapter_id]
    from mas.ctl.registry.catalog import UnknownComponentError, get_framework

    try:
        entry = get_framework(adapter_id)
    except UnknownComponentError:
        raise KeyError(f"unknown framework adapter: {adapter_id}") from None
    if entry.status in {"planned", "future_release"}:
        raise UnknownComponentError(f"framework {adapter_id!r} is not available yet")
    raise KeyError(f"unknown framework adapter: {adapter_id}")


def register_framework_adapter(adapter_id: FrameworkAdapterId, adapter: FrameworkAdapter) -> None:
    _ADAPTERS[adapter_id] = adapter
