#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.library.standard.lib.observability.native.transform import (
    NativeObservabilityTransform,
    TransformContext,
)
from mas.library.standard.plugins.observability.otel_plugin import OtelObservabilityPlugin
from mas.runtime.boundary.obs.transition import TransitionEvent


class _DummyConverter:
    def __init__(self) -> None:
        self.processed: list[dict] = []
        self.graph_calls: list[tuple[dict, dict]] = []
        self.flush_count = 0
        self._app_name = "sample-app"

    def process_event(self, rec: dict) -> None:
        self.processed.append(rec)

    def emit_graph_span(self, topology: dict, **kwargs) -> None:
        self.graph_calls.append((topology, kwargs))

    def flush_open_spans(self) -> None:
        self.flush_count += 1


def test_flush_emits_graph_span_from_projected_events(monkeypatch) -> None:
    records = [
        {
            "kind": "system_specification",
            "timestamp": 1.0,
            "agents": [{"id": "planner"}, {"id": "worker"}],
        },
        {
            "kind": "routing",
            "timestamp": 2.0,
            "source_agent_id": "planner",
            "target_agent_id": "worker",
            "call_id": "mas-1",
        },
    ]

    def fake_project_transition(*_args, **_kwargs):
        return records

    monkeypatch.setattr(
        "mas.library.standard.plugins.observability.otel_plugin.project_transition",
        fake_project_transition,
    )

    plugin = OtelObservabilityPlugin(
        converter=_DummyConverter(),
        context=TransformContext(agent_id="planner", run_id="run-1"),
        mas_id="sample-app",
        session_id="session-1",
    )

    plugin.on_transition(
        TransitionEvent(
            contract_id="orchestrator",
            mealy_symbol="user_input",
            phase="event",
            agent_id="planner",
            run_id="run-1",
            boundary_kind="session",
        )
    )
    plugin.flush()

    dummy = plugin.converter
    assert dummy is not None
    assert dummy.processed == records
    assert dummy.flush_count == 1
    assert len(dummy.graph_calls) == 1

    topology, kwargs = dummy.graph_calls[0]
    assert {node["id"] for node in topology["nodes"]} == {"planner", "worker"}
    assert kwargs["app_name"] == "sample-app"
    assert kwargs["parent_call_id"] is None


def test_on_transition_forwards_event_session_id_and_task_id_to_project_transition() -> None:
    """Regression: this is the SAME session_id/task_id fix
    native_plugin.py's on_transition got, applied to otel_plugin.py too — but
    unlike the native-plugin test, this one does NOT monkeypatch
    project_transition out of existence, since that would make the
    session_id=/task_id= arguments this test exists to check never actually
    execute. Runs the real project_transition/NativeObservabilityTransform,
    only faking the converter (process_event) at the boundary."""
    converter = _DummyConverter()
    plugin = OtelObservabilityPlugin(
        converter=converter,
        native_transform=NativeObservabilityTransform(),
        context=TransformContext(agent_id="planner", run_id="run-1"),
        mas_id="sample-app",
    )

    plugin.on_transition(
        TransitionEvent(
            contract_id="tool",
            mealy_symbol="TOOL_CALL",
            phase="start",
            agent_id="planner",
            run_id="run-1",
            session_id="live-session-id",
            task_id="live-task-id",
            correlation_id=1,
            boundary_kind="engine.io",
            attributes={"op": "TOOL_CALL", "tool_name": "lookup_schedule"},
        )
    )

    assert converter.processed, "expected at least one projected record"
    assert all(rec.get("session_id") == "live-session-id" for rec in converter.processed)
    assert all(rec.get("task_id") == "live-task-id" for rec in converter.processed)


def test_on_transition_falls_back_to_override_field_when_event_has_none() -> None:
    converter = _DummyConverter()
    plugin = OtelObservabilityPlugin(
        converter=converter,
        native_transform=NativeObservabilityTransform(),
        context=TransformContext(agent_id="planner", run_id="run-1"),
        mas_id="sample-app",
        session_id="override-session-id",
    )

    plugin.on_transition(
        TransitionEvent(
            contract_id="tool",
            mealy_symbol="TOOL_CALL",
            phase="start",
            agent_id="planner",
            run_id="run-1",
            correlation_id=1,
            boundary_kind="engine.io",
            attributes={"op": "TOOL_CALL", "tool_name": "lookup_schedule"},
        )
    )

    assert converter.processed
    assert all(rec.get("session_id") == "override-session-id" for rec in converter.processed)
