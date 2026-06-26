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
    "native": NativeFrameworkAdapter(),
    "langgraph": LangGraphFrameworkAdapter(),
}


def list_registered_adapters() -> list[str]:
    return sorted(_ADAPTERS.keys())


def get_framework_adapter(adapter_id: FrameworkAdapterId) -> FrameworkAdapter:
    if adapter_id not in _ADAPTERS:
        raise KeyError(f"unknown framework adapter: {adapter_id}")
    return _ADAPTERS[adapter_id]


def register_framework_adapter(adapter_id: FrameworkAdapterId, adapter: FrameworkAdapter) -> None:
    _ADAPTERS[adapter_id] = adapter
