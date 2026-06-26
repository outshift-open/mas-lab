#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Contract registry — canonical re-exports (implementations live in boundary/engine/machines)."""

from __future__ import annotations

from mas.runtime.boundary.context.protocol import CtxAssembler
from mas.runtime.boundary.hitl.responders import HitlResponder
from mas.runtime.boundary.obs.protocol import ObservabilitySink
from mas.runtime.engine.protocol import EngineContract
from mas.runtime.machines.design_pattern.protocol import DesignPatternPlugin, MealyPlugin

# Stable aliases (doc / schema IDs)
DesignPatternContract = MealyPlugin
CtxAssemblerContract = CtxAssembler

__all__ = [
    "CtxAssembler",
    "CtxAssemblerContract",
    "DesignPatternContract",
    "DesignPatternPlugin",
    "EngineContract",
    "HitlResponder",
    "MealyPlugin",
    "ObservabilitySink",
]
