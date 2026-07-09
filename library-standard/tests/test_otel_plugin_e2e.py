#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""End-to-end coverage for OtelObservabilityPlugin with a real converter:
build_otel_converter / create_otel_plugin / from_binding / reset_run / close,
plus the regression guard that from_binding does not import a missing module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mas.library.standard.lib.observability.otel.converter import OTEL_AVAILABLE
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.transition import TransitionEvent

pytestmark = pytest.mark.skipif(not OTEL_AVAILABLE, reason="opentelemetry-sdk not installed")


def _otlp_exporter_available() -> bool:
    try:
        import opentelemetry.exporter.otlp.proto.http.trace_exporter  # noqa: F401
        return True
    except Exception:
        return False


_needs_otlp = pytest.mark.skipif(
    not _otlp_exporter_available(), reason="opentelemetry OTLP http exporter not installed"
)

_RECORDS = [
    {"kind": "system_specification", "timestamp": 1.0,
     "agents": [{"id": "planner"}, {"id": "worker"}], "app_name": "sample-app"},
    {"kind": "mas_call_start", "call_id": "mas-1", "timestamp": 1.0,
     "agent_id": "planner", "run_id": "r1", "session_id": "s1"},
    {"kind": "routing", "timestamp": 2.0, "source_agent_id": "planner",
     "target_agent_id": "worker", "call_id": "mas-1"},
    {"kind": "mas_call_end", "call_id": "mas-1", "status": "success", "timestamp": 3.0},
]


def _patch_projection(monkeypatch) -> None:
    monkeypatch.setattr(
        "mas.library.standard.plugins.observability.otel_plugin.project_transition",
        lambda *_a, **_k: _RECORDS,
    )


def _transition() -> TransitionEvent:
    return TransitionEvent(
        contract_id="orchestrator", mealy_symbol="user_input", phase="event",
        agent_id="planner", run_id="r1", boundary_kind="session",
    )


def test_create_otel_plugin_full_lifecycle(tmp_path: Path, monkeypatch) -> None:
    from mas.library.standard.lib.observability.native.transform import TransformContext
    from mas.library.standard.plugins.observability.otel_plugin import create_otel_plugin

    _patch_projection(monkeypatch)
    spans_path = tmp_path / "traces" / "otel_sdk_spans.jsonl"
    plugin = create_otel_plugin(
        spans_path=spans_path,
        context=TransformContext(agent_id="planner", run_id="r1"),
        app_name="sample-app",
    )
    plugin.on_transition(_transition())
    plugin.flush()
    blob = spans_path.read_text()
    # real spans + the <app>.graph topology span, with the mas_call_start as parent
    assert "sample-app.graph" in blob
    assert "gen_ai.ioa.graph" in blob

    # reset_run clears converter/projection state (file truncates on next export)
    plugin.reset_run()
    assert plugin._projected_events == []
    assert plugin._graph_emitted is False

    plugin.close()  # flush + provider.shutdown(), no error


@_needs_otlp
def test_build_otel_converter_with_otlp_endpoint(tmp_path: Path, monkeypatch) -> None:
    # A configured OTLP endpoint adds the OTLP exporter branch.
    from mas.library.standard.plugins.observability.otel_plugin import build_otel_converter

    provider, converter, file_exporter = build_otel_converter(
        spans_path=tmp_path / "s.jsonl",
        otlp_endpoint="http://localhost:4318/",
    )
    assert converter is not None
    provider.shutdown()


def test_from_binding_constructs_plugin_without_missing_module(tmp_path: Path, monkeypatch) -> None:
    """Regression: from_binding used to import a non-existent
    ...plugins.observability.registry module and crash with ModuleNotFoundError."""
    from mas.library.standard.plugins.observability.otel_plugin import OtelObservabilityPlugin

    _patch_projection(monkeypatch)
    events_file = tmp_path / "traces" / "events.jsonl"
    events_file.parent.mkdir(parents=True)
    events_file.write_text("", encoding="utf-8")

    binding = ObservabilityBinding(
        plugins=["otel"],
        plugin_configs={"otel": {"service_name": "svc", "app_name": "sample-app"}},
        events_file=str(events_file),
    )
    plugin = OtelObservabilityPlugin.from_binding(binding, base_dir=tmp_path, agent_id="planner")
    assert plugin is not None
    assert plugin.spans_path == (tmp_path / "traces" / "otel_sdk_spans.jsonl")

    plugin.on_transition(_transition())
    plugin.close()
    assert (tmp_path / "traces" / "otel_sdk_spans.jsonl").read_text()


@_needs_otlp
def test_from_binding_honours_env_otlp_endpoint(tmp_path: Path, monkeypatch) -> None:
    from mas.library.standard.plugins.observability.otel_plugin import OtelObservabilityPlugin

    monkeypatch.setenv("MY_OTLP", "http://localhost:4318")
    binding = ObservabilityBinding(
        plugins=["otel"],
        plugin_configs={"otel": {"output_path": str(tmp_path / "out.jsonl")}},
        otlp_endpoint_env="MY_OTLP",
    )
    plugin = OtelObservabilityPlugin.from_binding(binding, base_dir=tmp_path, agent_id="a")
    assert plugin is not None
    assert plugin.spans_path == (tmp_path / "out.jsonl")
    plugin.close()
