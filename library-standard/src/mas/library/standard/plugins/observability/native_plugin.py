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

    def __post_init__(self) -> None:
        if self.emitters:
            self._fanout = FanOutEmitter(*self.emitters)

    def on_transition(self, event: TransitionEvent) -> None:
        if self._fanout is None:
            return
        for rec in project_transition(
            event,
            transforms=self.transforms,
            ctx=self.context,
            mas_id=self.mas_id,
            session_id=self.session_id,
        ):
            self._fanout.emit(rec)

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
