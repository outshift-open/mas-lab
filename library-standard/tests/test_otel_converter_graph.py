#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Focused coverage for the graph-span emission added to MasOtelConverter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mas.library.standard.lib.observability.otel.converter import OTEL_AVAILABLE

pytestmark = pytest.mark.skipif(not OTEL_AVAILABLE, reason="opentelemetry-sdk not installed")


def _make_converter(output_path: Path):
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from mas.library.standard.lib.observability.otel.converter import (
        JSONLineFileSpanExporter,
        MasOtelConverter,
    )

    provider = TracerProvider(resource=Resource.create({"service.name": "t"}))
    provider.add_span_processor(SimpleSpanProcessor(JSONLineFileSpanExporter(output_path)))
    tracer = provider.get_tracer("t")
    return MasOtelConverter(tracer, app_name="my-app"), provider


def test_emit_graph_span_empty_topology_emits_nothing(tmp_path: Path) -> None:
    out = tmp_path / "spans.jsonl"
    converter, provider = _make_converter(out)
    converter.emit_graph_span({"nodes": [], "edges": []})
    provider.force_flush()
    provider.shutdown()
    assert not out.exists() or out.read_text().strip() == ""


def test_emit_graph_span_uses_converter_app_name(tmp_path: Path) -> None:
    out = tmp_path / "spans.jsonl"
    converter, provider = _make_converter(out)
    topo = {"nodes": [{"id": "a", "name": "a"}], "edges": []}
    converter.emit_graph_span(topo, ts_ns=1_000_000_000, protocol="A2A")
    provider.force_flush()
    provider.shutdown()
    blob = out.read_text()
    assert "my-app.graph" in blob
    assert "A2A" in blob


def test_point_with_call_id_sets_attribute(tmp_path: Path) -> None:
    out = tmp_path / "spans.jsonl"
    converter, provider = _make_converter(out)
    converter._point("pt", {"k": "v"}, call_id="call-123", ts_ns=1_000_000_000)
    provider.force_flush()
    provider.shutdown()
    spans = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert any(s["attributes"].get("mas.call.id") == "call-123" for s in spans)
