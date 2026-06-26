#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""RuntimeBuilder — ctl-facing entry (no direct kernel import from consumers)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from mas.runtime.boundary.hitl.responders import HitlResponder
from mas.runtime.engine.simulated import SimulatedEngine
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.driver.instance import RuntimeInstance


@dataclass
class RuntimeBuilder:
    """Construct embeddable RuntimeInstance from config and optional adapters."""

    config: KernelConfig = field(default_factory=KernelConfig)
    hitl: HitlResponder | None = None
    engine: SimulatedEngine | None = field(default_factory=SimulatedEngine)
    ctx: Any | None = None
    enable_observability: bool = True
    enable_governance: bool = True
    enable_coordination: bool = True

    def build(self) -> RuntimeInstance:
        config = self.config
        if not self.enable_governance:
            config = replace(config, enable_governance=False)
        if not self.enable_observability:
            config = replace(
                config,
                enable_envelope_observability=False,
            )
        return RuntimeInstance.from_parts(
            config=config,
            hitl=self.hitl,
            engine=self.engine,
            ctx=self.ctx,
            enable_observability=self.enable_observability,
            enable_coordination=self.enable_coordination,
        )

    @classmethod
    def from_config(cls, config: KernelConfig, **kwargs: Any) -> RuntimeInstance:
        return cls(config=config, **kwargs).build()
