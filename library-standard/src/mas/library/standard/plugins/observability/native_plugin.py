#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""NativeObservabilityPlugin — read-mode export: TransitionEvent → events.jsonl."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.library.standard.lib.observability.emit import EventEmitter, FanOutEmitter
from mas.library.standard.lib.observability.native.emit_transition import project_transition
from mas.library.standard.lib.observability.native.transform import NativeObservabilityTransform, TransformContext
from mas.runtime.boundary.obs.observability_plugin import ObservabilityPlugin
from mas.runtime.boundary.obs.transition import TransitionEvent


@dataclass
class NativeObservabilityPlugin(ObservabilityPlugin):
    """Project kernel transitions to native ``events.jsonl`` (library-standard, read mode)."""

    plugin_id: str = "native_observability@v1"
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


__all__ = ["NativeObservabilityPlugin"]
