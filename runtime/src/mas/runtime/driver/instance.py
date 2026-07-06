#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""RuntimeInstance — embeddable control-plane surface for ctl and integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from mas.runtime.boundary.obs.binding import ObservabilityBinding
    from mas.runtime.boundary.obs.loader import ObsPluginSet


@dataclass
class RuntimeInstance:
    """Wraps kernel + driver; exposes pause/resume/abort and user feed."""

    kernel: RuntimeKernel
    driver: KernelDriver
    _checkpoints: list[dict] = field(default_factory=list)
    obs_plugin_set: Any | None = field(default=None, repr=False)

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
        obs_binding: ObservabilityBinding | None = None,
        obs_base_dir: Path | None = None,
        obs_agent_id: str | None = None,
    ) -> RuntimeInstance:
        kernel = RuntimeKernel(config=config or KernelConfig())
        op = ObservabilityOperator() if enable_observability else None
        driver = KernelDriver(
            kernel=kernel,
            hitl=hitl,
            engine=engine or SimulatedEngine(),
            ctx=ctx or AutoCtxAssembler(),
            observability=op,
            coordination=ChokepointCoordinator() if enable_coordination else None,
        )
        instance = cls(kernel=kernel, driver=driver)

        if obs_binding is not None and op is not None:
            from mas.runtime.boundary.obs.loader import ObsPluginSet, load_obs_plugins

            plugins = load_obs_plugins(
                obs_binding,
                base_dir=obs_base_dir or Path("."),
                agent_id=obs_agent_id,
            )
            plugin_set = ObsPluginSet(plugins=plugins)
            plugin_set.subscribe_to(
                op,
                agent_id=obs_agent_id or "agent",
            )
            instance.obs_plugin_set = plugin_set

        return instance

    @classmethod
    def from_spec(
        cls,
        spec: dict,
        *,
        base_dir: Any | None = None,
        agent_id: str = "agent",
        obs_binding_override: ObservabilityBinding | None = None,
        hitl: Any | None = None,
        engine: Any | None = None,
        ctx: Any | None = None,
        enable_coordination: bool = True,
        enable_governance: bool = True,
        enable_observability: bool = True,
    ) -> RuntimeInstance:
        """Build a RuntimeInstance from a raw agent spec dict.

        This is the production entry point for spec-driven instantiation.
        ctl may pass obs_binding_override when CLI flags supersede spec defaults.

        ``spec`` is the inner ``spec:`` block of an agent manifest, e.g.
        ``manifest["spec"]``.
        """
        from dataclasses import replace as _replace
        from pathlib import Path as _Path

        from mas.runtime.spec.parser import parse_agent_spec

        kernel_config, spec_obs_binding = parse_agent_spec(spec)
        obs_binding = obs_binding_override if obs_binding_override is not None else spec_obs_binding
        resolved_base_dir = (_Path(base_dir) if isinstance(base_dir, str) else base_dir) or _Path(".")

        if not enable_governance:
            kernel_config = _replace(kernel_config, enable_governance=False)

        return cls.from_parts(
            config=kernel_config,
            hitl=hitl,
            engine=engine,
            ctx=ctx,
            obs_binding=obs_binding,
            obs_base_dir=resolved_base_dir,
            obs_agent_id=agent_id,
            enable_coordination=enable_coordination,
            enable_observability=enable_observability,
        )

    def pause(self, *, reason: str = "") -> DriverTrace:
        return self.driver.feed(LifecyclePause(reason=reason))

    def resume(self) -> DriverTrace:
        return self.driver.feed(LifecycleResume())

    def abort(self, *, reason: str = "") -> DriverTrace:
        return self.driver.feed(LifecycleAbort(reason=reason))

    def feed(self, event: IngressSymbol) -> DriverTrace:
        return self.driver.feed(event)

    def run_user_text(self, text: str, *, turn_id: str = "u1") -> DriverTrace:
        op = self.driver.observability
        exec_id: str | None = None
        if op is not None and self.obs_plugin_set is not None:
            agent_id = op._agent_id or "agent"
            exec_id = f"{agent_id}-{turn_id}-exec"
            op.push_call_frame(exec_id)
            op.record_session("user_input", text=text, call_id=exec_id, turn_id=turn_id)

        trace = self.feed(UserInputReceived(user_turn_id=turn_id, text=text))

        if op is not None and exec_id is not None:
            response_text = "\n".join(
                r.content for r in trace.client_responses if getattr(r, "content", "")
            ).strip()
            if response_text:
                op.record_session("agent_response", text=response_text, finish_reason="stop")
            op.pop_call_frame(exec_id)

        return trace

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
