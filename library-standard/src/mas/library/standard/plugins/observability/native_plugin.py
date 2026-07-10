#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""NativeObservabilityPlugin — read-mode export: TransitionEvent → events.jsonl."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.library.standard.lib.observability.emit import EventEmitter, FanOutEmitter
from mas.library.standard.lib.observability.native.emit_transition import project_transition
from mas.library.standard.lib.observability.native.transform import NativeObservabilityTransform, TransformContext
from mas.runtime.boundary.obs.observability_plugin import ObservabilityPlugin
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.transition import TransitionEvent


@dataclass
class NativeObservabilityPlugin(ObservabilityPlugin):
    """Project kernel transitions to native ``events.jsonl`` (library-standard, read mode)."""

    plugin_id: str = "native_observability@v1"
    implements = ["observability"]
    transforms: list = field(default_factory=lambda: [NativeObservabilityTransform()])
    emitters: list[EventEmitter] = field(default_factory=list)
    context: TransformContext = field(default_factory=TransformContext)
    mas_id: str = ""
    session_id: str = ""
    _fanout: FanOutEmitter | None = field(default=None, init=False)
    _ctx_by_agent: dict[str, TransformContext] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.emitters:
            self._fanout = FanOutEmitter(*self.emitters)

    def _ctx_for(self, agent_id: str) -> TransformContext:
        """Per-agent TransformContext.

        A single plugin set is shared across every agent in a multi-agent run
        (see ``setup_shared_obs``), but each agent runs its own turns with its
        own session/correlation state (exec_call_id, call-id pairing, dedup
        sets).  Sharing one context would cross-contaminate that state — a
        delegated sub-agent's ``user_input`` would reset the entry agent's
        tracking — and stamp every record with the entry agent's id.  Keep one
        context per agent so records carry the correct ``agent_id`` and each
        agent's ``*_start``/``*_end`` pairing stays isolated.

        Run-global scope (``run_id``, ``mas_call_id``) is seeded from the shared
        base context so that, e.g., every agent's ``execution_start`` parents to
        the same MAS call — those values are not per-agent.
        """
        key = agent_id or self.context.agent_id or "agent"
        ctx = self._ctx_by_agent.get(key)
        if ctx is None:
            ctx = TransformContext(
                agent_id=key,
                run_id=self.context.run_id,
                mas_call_id=self.context.mas_call_id,
            )
            self._ctx_by_agent[key] = ctx
        elif self.context.mas_call_id and not ctx.mas_call_id:
            # MAS call opened after this agent's context was created.
            ctx.mas_call_id = self.context.mas_call_id
        return ctx

    def on_transition(self, event: TransitionEvent) -> None:
        if self._fanout is None:
            return
        ctx = self._ctx_for(event.agent_id)
        for rec in project_transition(
            event,
            transforms=self.transforms,
            ctx=ctx,
            mas_id=self.mas_id,
            session_id=self.session_id,
        ):
            self._fanout.emit(rec)
        # Propagate run-global MAS call id back to the shared base so contexts
        # created for other agents afterwards inherit it (mas_call_start is
        # emitted on the "mas" pseudo-agent, before sub-agent contexts exist).
        if ctx.mas_call_id and not self.context.mas_call_id:
            self.context.mas_call_id = ctx.mas_call_id

    def flush(self) -> None:
        if self._fanout:
            self._fanout.flush()

    def close(self) -> None:
        if self._fanout:
            self._fanout.close()

    @classmethod
    def from_binding(
        cls,
        binding: ObservabilityBinding,
        *,
        base_dir: str | Path,
        agent_id: str,
    ) -> "NativeObservabilityPlugin":
        from pathlib import Path

        from mas.library.standard.lib.observability.emit import JsonlFileEmitter, StdoutJsonlEmitter

        base_path = Path(base_dir)
        native_cfg = binding.plugin_configs.get("native") or {}
        events_path = Path(binding.events_file) if binding.events_file else base_path / "traces" / "events.jsonl"
        if native_cfg.get("path"):
            p = Path(str(native_cfg["path"]))
            events_path = p if p.is_absolute() else (base_path / p).resolve()
        else:
            events_path = events_path if events_path.is_absolute() else events_path.resolve()

        emitters = []
        if binding.stdout:
            emitters.append(StdoutJsonlEmitter())
        emitters.insert(0, JsonlFileEmitter(events_path))

        return cls(
            transforms=[NativeObservabilityTransform()],
            emitters=emitters,
            context=TransformContext(agent_id=agent_id, run_id=""),
        )


__all__ = ["NativeObservabilityPlugin"]
