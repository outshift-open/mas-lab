#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability pipeline — transform chain then emit sinks (no duplicated I/O)."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field

from mas.ctl.adapters.obs.emit import EventEmitter, FanOutEmitter, JsonlFileEmitter, NullEmitter, StdoutJsonlEmitter
from mas.ctl.adapters.obs.transform import (
    BoundaryPassthroughTransform,
    EventTransform,
    NativeObservabilityTransform,
    OtelSpanTransform,
    TransformContext,
)
from mas.runtime.schema.observability import ObservabilityEvent


@dataclass
class ObservabilityPipeline:
    """Apply transforms then fan-out to emitters."""

    transforms: list[EventTransform] = field(default_factory=list)
    emitters: list[EventEmitter] = field(default_factory=list)
    context: TransformContext = field(default_factory=TransformContext)
    _fanout: FanOutEmitter | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.emitters:
            self._fanout = FanOutEmitter(*self.emitters)
        if not self.context.run_id:
            self.context.run_id = os.environ.get("UI_RUN_ID") or f"run-{uuid.uuid4().hex[:12]}"

    def ingest(self, record: dict) -> None:
        if not self._fanout:
            return
        records = [dict(record)]
        for transform in self.transforms:
            next_records: list[dict] = []
            for rec in records:
                next_records.extend(transform.transform(rec, ctx=self.context))
            records = next_records
        for rec in records:
            rec.setdefault("timestamp", time.time())
            self._fanout.emit(rec)

    def ingest_boundary(self, event: ObservabilityEvent) -> None:
        payload = event.model_dump(mode="json")
        payload["_source"] = "boundary"
        self.ingest(payload)

    def ingest_session(self, session_kind: str, **fields: object) -> None:
        self.ingest({"_source": "session", "session_kind": session_kind, **fields})

    def flush(self) -> None:
        if self._fanout:
            self._fanout.flush()

    def close(self) -> None:
        if self._fanout:
            self._fanout.close()


@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = False
    format: str = "native"  # native | boundary | both | otel
    events_file: str | None = None
    events_stdout: bool = False
    otel_file: str | None = None
    sink_ref: str | None = None
    agent_id: str = "agent"
    plugins: list[str] | None = None


def resolve_events_path(base_dir, config: ObservabilityConfig):
    from pathlib import Path

    if config.events_file:
        p = Path(config.events_file)
        return p if p.is_absolute() else (Path(base_dir) / p).resolve()
    return (Path(base_dir) / "traces" / "events.jsonl").resolve()


def build_pipeline(config: ObservabilityConfig, *, base_dir) -> ObservabilityPipeline | None:
    if not config.enabled:
        return None

    transforms: list[EventTransform] = []
    emitters: list[EventEmitter] = []

    plugins = config.plugins or []
    fmt = (config.sink_ref or config.format or "native").lower()
    if fmt in ("native", "native-jsonl", "infra:native", "infra:native-jsonl"):
        fmt = "native"

    if plugins:
        if "native" in plugins:
            transforms.append(NativeObservabilityTransform())
        if "otel" in plugins:
            transforms.append(OtelSpanTransform())
        if not transforms:
            transforms.append(NativeObservabilityTransform())
    else:
        if fmt in ("boundary", "both"):
            transforms.append(BoundaryPassthroughTransform())
        if fmt in ("native", "both", "otel", "infra:otel-local", "otel-local"):
            transforms.append(NativeObservabilityTransform())
        if fmt in ("otel", "infra:otel-local", "otel-local"):
            transforms.append(OtelSpanTransform())

        if not transforms:
            transforms.append(NativeObservabilityTransform())

    events_path = resolve_events_path(base_dir, config)
    emitters.append(JsonlFileEmitter(events_path))

    emit_otel = config.otel_file or fmt in ("otel", "infra:otel-local", "otel-local")
    if plugins:
        emit_otel = emit_otel or "otel" in plugins
    if emit_otel:
        from pathlib import Path

        otel_path = config.otel_file or str(Path(events_path).parent / "otel_sdk_spans.jsonl")
        emitters.append(JsonlFileEmitter(otel_path))

    if config.events_stdout:
        emitters.append(StdoutJsonlEmitter())

    ctx = TransformContext(agent_id=config.agent_id, run_id=os.environ.get("UI_RUN_ID", ""))
    return ObservabilityPipeline(transforms=transforms, emitters=emitters, context=ctx)


def parse_sink_from_deployment(deployment: dict | None) -> str | None:
    if not deployment:
        return None
    spec = deployment.get("spec") or {}
    shared = spec.get("shared") or {}
    if isinstance(shared, dict):
        ref = shared.get("observability_ref") or shared.get("sink_ref")
        if ref:
            return str(ref)
    obs = spec.get("observability") or {}
    if isinstance(obs, dict):
        return obs.get("backend") or obs.get("sink_ref")
    return None
