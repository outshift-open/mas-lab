#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LlmDelegator — delegate_to_* execution over CommBus."""

from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator


def test_llm_delegator_dispatches_via_run_turn():
    calls: list[tuple[str, str]] = []

    def run_turn(agent_id: str, prompt: str) -> str:
        calls.append((agent_id, prompt))
        return f"ok:{agent_id}"

    delegator = LlmDelegator(run_turn=run_turn)
    out = delegator.call_delegate_tool("delegate_to_telemetry", {"task": "check latency"})
    assert out == "ok:telemetry"
    assert calls == [("telemetry", "check latency")]


def test_llm_delegator_missing_target_on_bus():
    delegator = LlmDelegator(
        run_turn=lambda aid, task: (_ for _ in ()).throw(KeyError(aid)),
    )
    out = delegator.call_delegate_tool("delegate_to_missing", {"task": "x"})
    assert "not available on bus" in out


def test_llm_delegator_is_delegate_tool():
    delegator = LlmDelegator(run_turn=lambda aid, task: "ok")
    assert delegator.is_delegate_tool("delegate_to_x")
    assert not delegator.is_delegate_tool("delegate_to_")


def test_llm_delegator_caches_identical_task_per_session():
    calls: list[str] = []

    def run_turn(agent_id: str, prompt: str) -> str:
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

    def run_turn(agent_id: str, prompt: str) -> str:
        calls.append((agent_id, prompt))
        return f"findings:{agent_id}:{prompt}"

    delegator = LlmDelegator(run_turn=run_turn)
    assert delegator.delegate("telemetry", "task1") == "findings:telemetry:task1"
    assert delegator.delegate("telemetry", "task2") == "findings:telemetry:task2"
    assert calls == [("telemetry", "task1"), ("telemetry", "task2")]
