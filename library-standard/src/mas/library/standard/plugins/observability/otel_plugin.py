#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OtelObservabilityPlugin — read-mode export via MasOtelConverter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mas.library.standard.lib.observability.export_layers import ExportLayers, parse_export_layers
from mas.library.standard.lib.observability.native.emit_transition import project_transition
from mas.library.standard.lib.observability.native.transform import NativeObservabilityTransform, TransformContext
from mas.library.standard.lib.observability.otel.converter import OTEL_AVAILABLE, MasOtelConverter
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

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from mas.library.standard.lib.observability.otel.converter import JSONLineFileSpanExporter
    from mas.library.standard.plugins.observability.exporters import MultiSpanExporter

    exporters: list = [JSONLineFileSpanExporter(spans_path)]
    file_exporter = exporters[0]
    if otlp_endpoint:
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
    converter: MasOtelConverter | None = None
    native_transform: NativeObservabilityTransform = field(default_factory=NativeObservabilityTransform)
    context: TransformContext = field(default_factory=TransformContext)
    mas_id: str = ""
    session_id: str = ""
    spans_path: Path | None = None
    _provider: Any = field(default=None, init=False, repr=False)
    _file_exporter: Any = field(default=None, init=False, repr=False)

    def reset_run(self) -> None:
        """Clear converter state and truncate the span JSONL on the next export."""
        if self.converter is not None:
            self.converter.reset_run()
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
            self.converter.process_event(rec)

    def flush(self) -> None:
        if self.converter is not None:
            self.converter.flush_open_spans()
        if self._provider is not None:
            self._provider.force_flush()

    def close(self) -> None:
        self.flush()
        if self._provider is not None:
            self._provider.shutdown()


__all__ = ["OtelObservabilityPlugin", "build_otel_converter", "create_otel_plugin"]
