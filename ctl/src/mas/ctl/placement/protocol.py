#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Placement backend protocol — avoids circular imports with docker/k8s stubs."""

from __future__ import annotations

from typing import Protocol

from mas.ctl.compose.models import EffectiveBindManifest, PlacementPlan
from mas.ctl.placement.bus.inproc import InProcessCommBus
from mas.runtime.driver.instance import RuntimeInstance


class MaterializedRun:
    """Handles returned after placement backend materialize()."""

    def __init__(self) -> None:
        self.instances: dict[str, RuntimeInstance] = {}
        self.bus: InProcessCommBus | None = None


class PlacementBackend(Protocol):
    name: str

    def materialize(
        self, bind: EffectiveBindManifest, plan: PlacementPlan
    ) -> MaterializedRun:
        ...
