#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for library-standard observability projection."""

from __future__ import annotations

import json

from mas.library.standard.lib.observability.emit import JsonlFileEmitter
from mas.library.standard.lib.observability.native.envelope import stamp_envelope_fields
from mas.library.standard.plugins.observability.native_plugin import NativeObservabilityPlugin
from mas.library.standard.lib.observability.native.transform import NativeObservabilityTransform, TransformContext
from mas.runtime.boundary.obs.transition import TransitionEvent


def test_stamp_envelope_fields_llm_call() -> None:
    rec = stamp_envelope_fields({"kind": "llm_call_start", "run_id": "run-1"})
    assert rec["block"] == "execution"
    assert rec["summand"] == "model"
    assert rec["mealy_symbol"] == "LLM_CALL"


def test_native_plugin_emits_tool_call_with_parent(tmp_path) -> None:
    events_path = tmp_path / "events.jsonl"
    ctx = TransformContext(agent_id="sre", run_id="run-deleg", mas_call_id="mas-1", exec_call_id="exec-1")
    plugin = NativeObservabilityPlugin(
        transforms=[NativeObservabilityTransform()],
        emitters=[JsonlFileEmitter(events_path)],
        context=ctx,
        mas_id="sre-triage",
    )
    plugin.on_transition(
        TransitionEvent(
            contract_id="tool",
            mealy_symbol="TOOL_CALL",
            phase="start",
            agent_id="sre",
            run_id="run-deleg",
            correlation_id=9,
            call_id="tool-uuid-9",
            parent_call_id="exec-1",
            boundary_kind="engine.io",
            attributes={
                "op": "TOOL_CALL",
                "tool_name": "delegate_to_telemetry",
                "tool_arguments": {"task": "check"},
            },
        )
    )
    event = json.loads(events_path.read_text().strip())
    assert event["parent_call_id"] == "exec-1"
    assert event["call_id"] == "tool-uuid-9"


def test_session_execution_start_parents_to_mas_call(tmp_path) -> None:
    events_path = tmp_path / "events.jsonl"
    ctx = TransformContext(agent_id="sre", run_id="run-1", turn_id="t1", mas_call_id="mas-root")
    plugin = NativeObservabilityPlugin(
        transforms=[NativeObservabilityTransform()],
        emitters=[JsonlFileEmitter(events_path)],
        context=ctx,
    )
    plugin.on_transition(
        TransitionEvent(
            contract_id="orchestrator",
            mealy_symbol="user_input",
            phase="event",
            agent_id="sre",
            run_id="run-1",
            boundary_kind="session",
            attributes={"text": "hello", "call_id": f"{ctx.turn_id}-exec"},
        )
    )
    lines = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert lines[0]["kind"] == "execution_start"
    assert lines[0]["parent_call_id"] == "mas-root"


def test_native_plugin_emits_tool_call(tmp_path) -> None:
    events_path = tmp_path / "events.jsonl"
    plugin = NativeObservabilityPlugin(
        transforms=[NativeObservabilityTransform()],
        emitters=[JsonlFileEmitter(events_path)],
        context=TransformContext(agent_id="sre", run_id="run-1"),
        mas_id="sre-triage",
    )
    plugin.on_transition(
        TransitionEvent(
            contract_id="tool",
            mealy_symbol="TOOL_CALL",
            phase="start",
            agent_id="sre",
            run_id="run-1",
            correlation_id=3,
            boundary_kind="engine.io",
            attributes={
                "op": "TOOL_CALL",
                "tool_name": "delegate_to_telemetry",
                "tool_arguments": {"task": "check"},
            },
        )
    )
    event = json.loads(events_path.read_text().strip())
    assert event["kind"] == "tool_call_start"
    assert event["tool_name"] == "delegate_to_telemetry"
    assert event["mas_id"] == "sre-triage"
