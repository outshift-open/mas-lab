#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OtelObservabilityPlugin — read-mode export via MasOtelConverter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mas.library.standard.lib.observability.export_layers import ExportLayers, parse_export_layers
from mas.library.standard.lib.observability.native.emit_transition import project_transition
from mas.library.standard.lib.observability.native.transform import NativeObservabilityTransform, TransformContext
from mas.library.standard.lib.observability.otel.converter import OTEL_AVAILABLE, MasOtelConverter
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.observability_plugin import ObservabilityPlugin
from mas.runtime.boundary.obs.transition import TransitionEvent


def build_otel_converter(
    *,
    spans_path: Path,
    service_name: str = "mas-runtime",
    app_name: str = "",
    otlp_endpoint: str | None = None,
    export_layers: ExportLayers | None = None,
) -> tuple[Any, MasOtelConverter, Any]:
    if not OTEL_AVAILABLE:
        raise RuntimeError("opentelemetry-sdk is not installed (library-standard[otel])")

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from mas.library.standard.lib.observability.otel.converter import JSONLineFileSpanExporter
    from mas.library.standard.plugins.observability.exporters import MultiSpanExporter

    exporters: list = [JSONLineFileSpanExporter(spans_path)]
    file_exporter = exporters[0]
    if otlp_endpoint:
        # Only require the (optional) OTLP HTTP exporter package when an
        # endpoint is actually configured; file-only export must not depend
        # on it (OTEL_AVAILABLE only guarantees the SDK, not this exporter).
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporters.append(OTLPSpanExporter(endpoint=f"{otlp_endpoint.rstrip('/')}/v1/traces"))

    resource = Resource.create(
        {
            "service.name": service_name,
            "mas.instrumentation.version": "1.0.0",
            "mas.plugin": "OtelObservabilityPlugin",
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(MultiSpanExporter(exporters)))
    tracer = provider.get_tracer("mas-otel")
    converter = MasOtelConverter(tracer, app_name=app_name or service_name, export_layers=export_layers)
    return provider, converter, file_exporter


def create_otel_plugin(
    *,
    spans_path: Path,
    context: TransformContext,
    mas_id: str = "",
    session_id: str = "",
    service_name: str = "mas-runtime",
    app_name: str = "",
    otlp_endpoint: str | None = None,
    export_layers: ExportLayers | None = None,
) -> OtelObservabilityPlugin:
    provider, converter, file_exporter = build_otel_converter(
        spans_path=spans_path,
        service_name=service_name,
        app_name=app_name,
        otlp_endpoint=otlp_endpoint,
        export_layers=export_layers,
    )
    plugin = OtelObservabilityPlugin(
        converter=converter,
        context=context,
        mas_id=mas_id,
        session_id=session_id,
        spans_path=spans_path,
    )
    plugin._provider = provider
    plugin._file_exporter = file_exporter
    return plugin


@dataclass
class OtelObservabilityPlugin(ObservabilityPlugin):
    plugin_id: str = "otel_observability@v1"
    implements = ["observability"]
    converter: MasOtelConverter | None = None
    native_transform: NativeObservabilityTransform = field(default_factory=NativeObservabilityTransform)
    context: TransformContext = field(default_factory=TransformContext)
    mas_id: str = ""
    session_id: str = ""
    spans_path: Path | None = None
    _projected_events: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _graph_emitted: bool = field(default=False, init=False, repr=False)
    _provider: Any = field(default=None, init=False, repr=False)
    _file_exporter: Any = field(default=None, init=False, repr=False)

    def reset_run(self) -> None:
        """Clear converter state and truncate the span JSONL on the next export."""
        if self.converter is not None:
            self.converter.reset_run()
        self._projected_events.clear()
        self._graph_emitted = False
        if self._file_exporter is not None and self.spans_path is not None:
            self.spans_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_exporter.set_path(self.spans_path)
            self._file_exporter.reset()

    def on_transition(self, event: TransitionEvent) -> None:
        if self.converter is None:
            return
        for rec in project_transition(
            event,
            transforms=[self.native_transform],
            ctx=self.context,
            mas_id=self.mas_id,
            session_id=self.session_id,
        ):
            self._projected_events.append(rec)
            self.converter.process_event(rec)

    def flush(self) -> None:
        if self.converter is not None and self._projected_events and not self._graph_emitted:
            from mas.library.standard.lib.observability.otel.topology import (
                build_topology,
                derive_app_name,
                has_topology,
            )

            topology = build_topology(self._projected_events)
            if has_topology(topology):
                earliest_ts = next(
                    (e.get("timestamp") for e in self._projected_events if e.get("timestamp") is not None),
                    None,
                )
                graph_ts_ns = int(earliest_ts * 1_000_000_000) if earliest_ts is not None else None
                root_call_id = next(
                    (
                        str(e["call_id"])
                        for e in self._projected_events
                        if e.get("kind") == "mas_call_start" and e.get("call_id")
                    ),
                    None,
                )
                app_name = derive_app_name(
                    self._projected_events,
                    fallback=getattr(self.converter, "_app_name", "") or "",
                )
                self.converter.emit_graph_span(
                    topology,
                    app_name=app_name,
                    ts_ns=graph_ts_ns,
                    parent_call_id=root_call_id,
                )
                self._graph_emitted = True
        if self.converter is not None:
            self.converter.flush_open_spans()
        if self._provider is not None:
            self._provider.force_flush()

    def close(self) -> None:
        self.flush()
        if self._provider is not None:
            self._provider.shutdown()

    @classmethod
    def from_binding(
        cls,
        binding: ObservabilityBinding,
        *,
        base_dir: str | Path,
        agent_id: str,
    ) -> "OtelObservabilityPlugin" | None:
        from pathlib import Path

        otel_cfg = binding.plugin_configs.get("otel") or {}
        try:
            from mas.library.standard.plugins.observability.otel_plugin import create_otel_plugin
        except (ImportError, RuntimeError):
            return None

        from mas.library.standard.lib.observability.export_layers import parse_export_layers
        from mas.library.standard.lib.observability.native.transform import TransformContext

        base_path = Path(base_dir)
        events_path = binding.events_file or str(base_path / "traces" / "events.jsonl")
        out = otel_cfg.get("output_path") or otel_cfg.get("otel_file")
        if out:
            out_path = Path(str(out))
            spans_path_str = str(out_path if out_path.suffix == ".jsonl" else out_path / "otel_sdk_spans.jsonl")
        else:
            spans_path_str = str(Path(events_path).parent / "otel_sdk_spans.jsonl")

        spans_path = Path(spans_path_str)
        if not spans_path.is_absolute():
            spans_path = (base_path / spans_path).resolve()

        # OTLP export only when an endpoint env var is set (mirrors the old
        # loader.py: from_binding always writes a spans file, so absent an
        # explicit endpoint we stay file-only rather than defaulting to
        # localhost:4318).
        env_name = str(
            otel_cfg.get("otlp_endpoint_env")
            or binding.otlp_endpoint_env
            or "OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        endpoint = os.environ.get(env_name, "").strip() or None

        service_name = str(otel_cfg.get("service_name") or agent_id or "mas-runtime")
        app_name = str(otel_cfg.get("app_name") or service_name)
        ctx = TransformContext(agent_id=agent_id, run_id="")
        return create_otel_plugin(
            spans_path=spans_path,
            context=ctx,
            mas_id="",
            service_name=service_name,
            app_name=app_name,
            otlp_endpoint=endpoint,
            export_layers=parse_export_layers(otel_cfg),
        )


__all__ = ["OtelObservabilityPlugin", "build_otel_converter", "create_otel_plugin"]
