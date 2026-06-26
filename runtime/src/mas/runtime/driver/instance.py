#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""RuntimeInstance — embeddable control-plane surface for ctl and integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mas.runtime.boundary.coordination.chokepoint import ChokepointCoordinator
from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.engine.simulated import SimulatedEngine
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.driver.driver import DriverTrace, KernelDriver
from mas.runtime.driver.mocks import AutoCtxAssembler
from mas.runtime.schema.ingress import (
    IngressSymbol,
    LifecycleAbort,
    LifecyclePause,
    LifecycleResume,
    UserInputReceived,
)


@dataclass
class RuntimeInstance:
    """Wraps kernel + driver; exposes pause/resume/abort and user feed."""

    kernel: RuntimeKernel
    driver: KernelDriver
    _checkpoints: list[dict] = field(default_factory=list)

    @classmethod
    def from_parts(
        cls,
        *,
        config: KernelConfig | None = None,
        hitl: Any | None = None,
        engine: SimulatedEngine | None = None,
        ctx: Any | None = None,
        enable_observability: bool = True,
        enable_coordination: bool = True,
    ) -> RuntimeInstance:
        kernel = RuntimeKernel(config=config or KernelConfig())
        driver = KernelDriver(
            kernel=kernel,
            hitl=hitl,
            engine=engine or SimulatedEngine(),
            ctx=ctx or AutoCtxAssembler(),
            observability=ObservabilityOperator() if enable_observability else None,
            coordination=ChokepointCoordinator() if enable_coordination else None,
        )
        return cls(kernel=kernel, driver=driver)

    def pause(self, *, reason: str = "") -> DriverTrace:
        return self.driver.feed(LifecyclePause(reason=reason))

    def resume(self) -> DriverTrace:
        return self.driver.feed(LifecycleResume())

    def abort(self, *, reason: str = "") -> DriverTrace:
        return self.driver.feed(LifecycleAbort(reason=reason))

    def feed(self, event: IngressSymbol) -> DriverTrace:
        return self.driver.feed(event)

    def run_user_text(self, text: str, *, turn_id: str = "u1") -> DriverTrace:
        return self.feed(UserInputReceived(user_turn_id=turn_id, text=text))

    def capture_session_baseline(self) -> None:
        """Record idle kernel state at session start (for /reset)."""
        self._session_baseline = self.snapshot()

    def reset_session(self) -> None:
        """Reset conversation context and kernel to session-start idle state."""
        from mas.runtime.machines.gov import gov_is_hitl_pending

        if gov_is_hitl_pending(self.kernel.q):
            raise RuntimeError("cannot reset while HITL is pending")
        baseline = getattr(self, "_session_baseline", None)
        if baseline:
            self.restore(baseline)
        ctx = self.driver.ctx
        reset_fn = getattr(ctx, "reset_conversation", None)
        if callable(reset_fn):
            reset_fn()
        engine = self.driver.engine
        while engine is not None:
            reset_engine = getattr(engine, "reset_turn_state", None)
            if callable(reset_engine):
                reset_engine()
            engine = getattr(engine, "inner", None)

    def snapshot(self) -> dict:
        return self.kernel.snapshot()

    def restore(self, data: dict) -> None:
        self.kernel.restore(data)

    def record_checkpoint(self, label: str = "") -> dict:
        snap = self.snapshot()
        snap["label"] = label
        self._checkpoints.append(snap)
        return snap

    def load_checkpoint(self, data: dict) -> None:
        self.restore(data)

    @property
    def checkpoints(self) -> list[dict]:
        return list(self._checkpoints)
