#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Placement backend registry — materialize EffectiveBind to running handles."""

from __future__ import annotations

from mas.ctl.placement.bus.adapter import RuntimeCommEndpoint
from mas.ctl.placement.bus.inproc import InProcessCommBus
from mas.ctl.placement.protocol import MaterializedRun, PlacementBackend
from mas.ctl.compose.framework_registry import get_framework_adapter
from mas.ctl.compose.kernel_registry import get_runtime_backend
from mas.ctl.compose.models import EffectiveBindManifest, PlacementPlan
from mas.runtime.driver.instance import RuntimeInstance


class LocalInprocBackend:
    name = "local-inproc"

    def materialize(
        self, bind: EffectiveBindManifest, plan: PlacementPlan
    ) -> MaterializedRun:
        run = MaterializedRun()
        bus = InProcessCommBus()
        infra = bind.resolved_infra
        kernel = get_runtime_backend(bind.runtime_id, resolved_infra=infra)
        for agent in bind.agents:
            raw = kernel.create_agent_runtime(bind, agent.agent_id)
            if not isinstance(raw, RuntimeInstance):
                raise TypeError(f"expected RuntimeInstance, got {type(raw)}")
            adapter = get_framework_adapter(agent.framework_adapter)
            wrapped = adapter.wrap(raw, bind, agent.agent_id)
            if isinstance(wrapped, RuntimeInstance):
                instance = wrapped
            elif hasattr(wrapped, "instance") and isinstance(wrapped.instance, RuntimeInstance):
                instance = wrapped.instance
            else:
                raise TypeError(f"adapter {agent.framework_adapter} returned unsupported handle")
            run.instances[agent.agent_id] = instance
            bus.register(agent.agent_id, RuntimeCommEndpoint(agent.agent_id, instance))
        run.bus = bus
        return run


_BACKENDS: dict[str, PlacementBackend] = {}
_CATALOG_REGISTERED = False


def _register_from_catalog() -> None:
    global _CATALOG_REGISTERED
    if _CATALOG_REGISTERED:
        return
    from mas.ctl.registry.catalog import get_placement, import_class, list_placement_ids

    for placement_id in list_placement_ids():
        if placement_id in _BACKENDS:
            continue
        entry = get_placement(placement_id)
        if entry.module:
            _BACKENDS[placement_id] = import_class(entry.module)()
    _CATALOG_REGISTERED = True


def list_registered_backends() -> list[str]:
    _register_from_catalog()
    return sorted(_BACKENDS.keys())


def get_placement_backend(strategy: str) -> PlacementBackend:
    _register_from_catalog()
    from mas.ctl.compose.placement_validate import validate_placement_strategy

    validate_placement_strategy(strategy)
    if strategy not in _BACKENDS:
        raise RuntimeError(
            f"placement strategy {strategy!r} is registered but has no backend "
            f"(available: {sorted(_BACKENDS)}); see component-registry.yaml"
        )
    return _BACKENDS[strategy]
