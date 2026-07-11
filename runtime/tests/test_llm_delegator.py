#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LlmDelegator — delegate_to_* execution over CommBus."""

from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator


def test_llm_delegator_dispatches_via_run_turn():
    calls: list[tuple[str, str, int, str]] = []

    def run_turn(agent_id: str, prompt: str, correlation_id: int, caller_call_id: str) -> str:
        calls.append((agent_id, prompt, correlation_id, caller_call_id))
        return f"ok:{agent_id}"

    delegator = LlmDelegator(run_turn=run_turn)
    out = delegator.call_delegate_tool(
        "delegate_to_telemetry", {"task": "check latency"}, correlation_id=7
    )
    assert out == "ok:telemetry"
    assert calls == [("telemetry", "check latency", 7, "")]


def test_llm_delegator_missing_target_on_bus():
    delegator = LlmDelegator(
        run_turn=lambda aid, task, cid, ccid: (_ for _ in ()).throw(KeyError(aid)),
    )
    out = delegator.call_delegate_tool("delegate_to_missing", {"task": "x"})
    assert "not available on bus" in out


def test_llm_delegator_is_delegate_tool():
    delegator = LlmDelegator(run_turn=lambda aid, task, cid, ccid: "ok")
    assert delegator.is_delegate_tool("delegate_to_x")
    assert not delegator.is_delegate_tool("delegate_to_")


def test_llm_delegator_caches_identical_task_per_session():
    calls: list[str] = []

    def run_turn(agent_id: str, prompt: str, correlation_id: int, caller_call_id: str) -> str:
        calls.append(agent_id)
        return f"findings:{agent_id}:{prompt}"

    delegator = LlmDelegator(run_turn=run_turn)
    assert delegator.delegate("telemetry", "task1") == "findings:telemetry:task1"
    cached = delegator.delegate("telemetry", "task1")
    assert "already consulted" in cached
    assert "findings:telemetry:task1" in cached
    assert calls == ["telemetry"]


def test_llm_delegator_different_tasks_call_peer_again():
    calls: list[tuple[str, str]] = []

    def run_turn(agent_id: str, prompt: str, correlation_id: int, caller_call_id: str) -> str:
        calls.append((agent_id, prompt))
        return f"findings:{agent_id}:{prompt}"

    delegator = LlmDelegator(run_turn=run_turn)
    assert delegator.delegate("telemetry", "task1") == "findings:telemetry:task1"
    assert delegator.delegate("telemetry", "task2") == "findings:telemetry:task2"
    assert calls == [("telemetry", "task1"), ("telemetry", "task2")]


def test_llm_delegator_passes_correlation_id_through_to_run_turn():
    """Regression: the delegate_to_* TOOL_CALL's own correlation_id must reach
    run_turn unchanged — it's how the caller resolves this specific sibling's
    own call_id when several delegate_to_* calls fire in one batch (see
    make_workflow_send / ObservabilityOperator.call_id_for)."""
    seen: list[int] = []

    def run_turn(agent_id: str, prompt: str, correlation_id: int, caller_call_id: str) -> str:
        seen.append(correlation_id)
        return "ok"

    delegator = LlmDelegator(run_turn=run_turn)
    delegator.call_delegate_tool("delegate_to_a", {"task": "t1"}, correlation_id=3)
    delegator.call_delegate_tool("delegate_to_b", {"task": "t2"}, correlation_id=9)
    assert seen == [3, 9]


def test_llm_delegator_passes_caller_call_id_through_to_run_turn():
    """caller_call_id (this TOOL_CALL's own resolved call_id, attached by the
    driver — see InvokeEngineIo.call_id) must reach run_turn unchanged, so
    the delegate's own execution_start.parent_call_id is a real, native
    value instead of something reconstructed downstream from timestamps."""
    seen: list[str] = []

    def run_turn(agent_id: str, prompt: str, correlation_id: int, caller_call_id: str) -> str:
        seen.append(caller_call_id)
        return "ok"

    delegator = LlmDelegator(run_turn=run_turn)
    delegator.call_delegate_tool(
        "delegate_to_a", {"task": "t1"}, correlation_id=3, caller_call_id="tool-call-abc"
    )
    assert seen == ["tool-call-abc"]
