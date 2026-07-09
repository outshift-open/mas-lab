#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability transition and subscriber tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.runtime.boundary.obs.observability_plugin import ObservabilityPlugin
from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.boundary.obs.plugins import ObsPluginSet, build_observability_plugins
from mas.runtime.boundary.obs.transition import TransitionEvent, boundary_event_to_transition
from mas.runtime.schema.observability import ObsEventKind, ObsPhase, ObservabilityEvent


@dataclass
class _CapturePlugin(ObservabilityPlugin):
    seen: list[TransitionEvent] = field(default_factory=list)

    def on_transition(self, event: TransitionEvent) -> None:
        self.seen.append(event)


def test_boundary_event_to_transition_llm_start() -> None:
    ev = ObservabilityEvent(
        seq=1,
        kind=ObsEventKind.ENGINE_IO,
        phase=ObsPhase.EXECUTE,
        machine_id="M_model",
        correlation_id=7,
        payload={"op": "LLM_CALL", "tool_name": ""},
    )
    t = boundary_event_to_transition(ev, agent_id="sre", run_id="run-abc")
    assert t.contract_id == "model"
    assert t.phase == "start"
    assert t.mealy_symbol == "LLM_CALL"
    assert t.call_id == "llm-7"


def test_operator_notifies_subscribers() -> None:
    op = ObservabilityOperator()
    cap = _CapturePlugin()
    op.subscribe(cap)
    op.set_context(agent_id="agent-1", run_id="run-1")
    op.record_engine_io(correlation_id=3, op="TOOL_CALL", tool_name="delegate_to_telemetry")
    assert len(cap.seen) == 1
    assert cap.seen[0].contract_id == "tool"
    assert cap.seen[0].phase == "start"
    assert cap.seen[0].attributes.get("tool_name") == "delegate_to_telemetry"
    assert cap.seen[0].call_id is not None
    op.record_engine_io_return(correlation_id=3, op="TOOL_CALL", text="ok")
    assert len(cap.seen) == 2
    assert cap.seen[1].call_id == cap.seen[0].call_id
    assert cap.seen[0].parent_call_id is None


def test_operator_call_stack_parent_call_id() -> None:
    op = ObservabilityOperator()
    cap = _CapturePlugin()
    op.subscribe(cap)
    op.push_call_frame("exec-001")
    op.record_engine_io(correlation_id=1, op="LLM_CALL")
    assert cap.seen[-1].parent_call_id == "exec-001"
    op.record_engine_io_return(correlation_id=1, op="LLM_CALL", text="hi")
    assert cap.seen[-1].parent_call_id == "exec-001"
    op.pop_call_frame()


def test_operator_record_session_notifies_subscribers() -> None:
    op = ObservabilityOperator()
    cap = _CapturePlugin()
    op.subscribe(cap)
    op.set_context(agent_id="sre", run_id="run-1")
    op.record_session("user_input", text="hi", call_id="t1-exec")
    assert len(cap.seen) == 1
    assert cap.seen[0].boundary_kind == "session"
    assert cap.seen[0].mealy_symbol == "user_input"


def test_native_plugin_exports_envelope_activity(tmp_path) -> None:
    from mas.runtime.boundary.obs.binding import ObservabilityBinding

    binding = ObservabilityBinding(
        plugins=["native"],
        plugin_configs={"native": {"path": "events.jsonl"}},
    )
    plugins = build_observability_plugins(binding, base_dir=tmp_path, agent_id="sre")
    assert plugins
    op = ObservabilityOperator()
    for plugin in plugins:
        op.subscribe(plugin)
    op.set_context(agent_id="sre", run_id="run-test")
    op.record_envelope_activity(
        symbol="CONTRACT_START",
        activity="contract_call",
        boundary="start",
        phase=ObsPhase.REQUEST,
        correlation_id=5,
        machine_id="M_obs",
        payload={"op": "LLM_CALL"},
    )
    op.drain_plugin_queue()
    events_path = tmp_path / "events.jsonl"
    assert events_path.stat().st_size > 0
    assert any("llm_call" in line for line in events_path.read_text().splitlines())


def test_operator_async_plugins_isolate_failures() -> None:
    class _BrokenPlugin(ObservabilityPlugin):
        def on_transition(self, event: TransitionEvent) -> None:
            raise RuntimeError("plugin boom")

    op = ObservabilityOperator()
    cap = _CapturePlugin()
    op.subscribe(_BrokenPlugin())
    op.subscribe(cap)
    op.enable_async_plugins()
    op.record_engine_io(correlation_id=1, op="LLM_CALL")
    op.drain_plugin_queue()
    assert len(cap.seen) == 1


def test_native_transform_memory_and_parallel_kinds() -> None:
    from mas.library.standard.lib.observability.native.transform import (
        NativeObservabilityTransform,
        TransformContext,
    )

    transform = NativeObservabilityTransform()
    ctx = TransformContext(agent_id="a1", run_id="r1")
    mem_start = transform.transform(
        {
            "_source": "boundary",
            "kind": ObsEventKind.ENGINE_IO.value,
            "correlation_id": 9,
            "payload": {"op": "MEMORY_OP"},
        },
        ctx=ctx,
    )
    assert any(r.get("kind") == "memory_call_start" for r in mem_start)

    parallel = transform.transform(
        {
            "_source": "boundary",
            "kind": ObsEventKind.ENVELOPE_ACTIVITY.value,
            "correlation_id": 10,
            "payload": {
                "activity": "parallel_group",
                "boundary": "start",
                "group_id": "grp-1",
                "tools": [{"tool_name": "t1"}, {"tool_name": "t2"}],
            },
        },
        ctx=ctx,
    )
    assert any(r.get("kind") == "parallel_group_start" for r in parallel)
