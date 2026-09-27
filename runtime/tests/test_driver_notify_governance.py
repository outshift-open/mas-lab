#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""driver.py's _notify_governance — dispatch, filtering, and fault isolation."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.runtime.boundary.gov.filter import GovTransitionFilter
from mas.runtime.boundary.gov.ingress_chain import RegisteredIngressPlugin
from mas.runtime.boundary.gov.transition import GovTransition
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.engine.simulated import SimulatedEngine
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import GovDecision
from mas.runtime.kernel.inflight import pending_for_validate
from mas.runtime.kernel.types import GovState, ModelState
from mas.runtime.schema.ingress import EngineIoReturn


@dataclass
class _RecordingGovPlugin:
    """No transition_filters() — must receive everything (empty means all)."""

    seen: list[GovTransition] = field(default_factory=list)

    def on_transition(self, transition: GovTransition) -> None:
        self.seen.append(transition)

    def evaluate_egress(self, intent, *, config):
        return GovDecision.ALLOW, "test", ""


@dataclass
class _FilteredGovPlugin:
    """Declares filters — only egress TOOL_CALL and ingress USER_INPUT_RECEIVED."""

    seen: list[GovTransition] = field(default_factory=list)

    def transition_filters(self) -> list[GovTransitionFilter]:
        return [
            GovTransitionFilter(hook="ingress", kind=("USER_INPUT_RECEIVED",)),
            GovTransitionFilter(hook="egress", op=("TOOL_CALL",)),
        ]

    def on_transition(self, transition: GovTransition) -> None:
        self.seen.append(transition)

    def evaluate_egress(self, intent, *, config):
        return GovDecision.ALLOW, "test", ""


@dataclass
class _RaisingGovPlugin:
    """transition_filters() raises — must land M_gov in ERROR, not crash the driver."""

    calls: int = 0

    def transition_filters(self):
        self.calls += 1
        raise RuntimeError("boom in transition_filters")

    def on_transition(self, transition: GovTransition) -> None:
        raise AssertionError("on_transition must not be reached if filters() raised")

    def evaluate_egress(self, intent, *, config):
        return GovDecision.ALLOW, "test", ""


@dataclass
class _RaisingOnTransitionPlugin:
    calls: int = 0

    def on_transition(self, transition: GovTransition) -> None:
        self.calls += 1
        raise RuntimeError("boom in on_transition")

    def evaluate_egress(self, intent, *, config):
        return GovDecision.ALLOW, "test", ""


@dataclass
class _RaisingEvaluateEgressPlugin:
    def evaluate_egress(self, intent, *, config):
        raise RuntimeError("boom in evaluate_egress")


@dataclass
class _RaisingOnEngineEgressPlugin:
    """Observer boom after ALLOW — engine I/O must not dispatch."""

    def transition_filters(self) -> list[GovTransitionFilter]:
        return [GovTransitionFilter(hook="egress", kind=("INVOKE_ENGINE_IO",))]

    def on_transition(self, transition: GovTransition) -> None:
        raise RuntimeError("boom on egress observe")

    def evaluate_egress(self, intent, *, config):
        return GovDecision.ALLOW, "test", ""


def _instance_with(plugin) -> RuntimeInstance:
    engine = SimulatedEngine(
        script={1: EngineIoReturn(correlation_id=1, response_kind="MODEL_TEXT", next_step="STOP", text="ok")}
    )
    inst = RuntimeInstance.from_parts(engine=engine, config=KernelConfig(egress_governance_plugin=plugin))
    inst.capture_session_baseline()
    return inst


def _assert_gov_plugin_error(inst: RuntimeInstance, trace, *, needle: str) -> None:
    assert inst.kernel.q.gov_state == GovState.ERROR.value
    assert trace.boundary_errors
    err = trace.boundary_errors[0]
    assert err.code == "GOV_PLUGIN_ERROR"
    assert needle in (err.message or "")
    assert err.recoverable is False


def test_on_transition_notifies_every_plugin_in_the_chain() -> None:
    from mas.runtime.boundary.gov.plugin import GovernancePluginChain

    first = _RecordingGovPlugin()
    second = _RecordingGovPlugin()
    engine = SimulatedEngine(
        script={1: EngineIoReturn(correlation_id=1, response_kind="MODEL_TEXT", next_step="STOP", text="ok")}
    )
    inst = RuntimeInstance.from_parts(
        engine=engine,
        config=KernelConfig(egress_governance_plugin=GovernancePluginChain([first, second])),
    )
    inst.capture_session_baseline()
    inst.run_user_text("hello")
    assert first.seen
    assert {t.kind for t in first.seen} == {t.kind for t in second.seen}


def test_plugin_without_on_transition_is_a_silent_no_op() -> None:
    """A governance plugin that only implements evaluate_egress (no
    on_transition at all) must not error — the hook is optional."""

    @dataclass
    class _DecisionOnlyPlugin:
        def evaluate_egress(self, intent, *, config):
            return GovDecision.ALLOW, "test", ""

    inst = _instance_with(_DecisionOnlyPlugin())
    trace = inst.run_user_text("hello")
    assert trace.client_responses or trace.steps


def test_no_filters_declared_receives_every_ingress_and_egress_symbol() -> None:
    plugin = _RecordingGovPlugin()
    inst = _instance_with(plugin)
    inst.run_user_text("hello")

    hooks = {(t.hook, t.kind) for t in plugin.seen}
    assert ("ingress", "USER_INPUT_RECEIVED") in hooks
    assert ("egress", "INVOKE_ENGINE_IO") in hooks
    assert ("ingress", "ENGINE_IO_RETURN") in hooks


def test_declared_filters_admit_only_matching_transitions_or_semantics() -> None:
    plugin = _FilteredGovPlugin()
    inst = _instance_with(plugin)
    inst.run_user_text("hello")

    kinds = {t.kind for t in plugin.seen}
    # USER_INPUT_RECEIVED (ingress filter) and INVOKE_ENGINE_IO (egress
    # TOOL_CALL filter — LLM_CALL doesn't match op=("TOOL_CALL",) so it's
    # excluded too) — this script only ever issues an LLM_CALL, not a tool
    # call, so INVOKE_ENGINE_IO for LLM_CALL must NOT appear.
    assert kinds == {"USER_INPUT_RECEIVED"}
    assert not any(t.kind == "ENGINE_IO_RETURN" for t in plugin.seen)


def test_transition_filters_exception_moves_gov_to_error() -> None:
    plugin = _RaisingGovPlugin()
    inst = _instance_with(plugin)
    trace = inst.run_user_text("hello")
    assert plugin.calls > 0
    _assert_gov_plugin_error(inst, trace, needle="boom in transition_filters")
    assert not any(t.ingress.__class__.__name__ == "EngineIoReturn" for t in trace.steps)


def test_on_transition_exception_moves_gov_to_error() -> None:
    plugin = _RaisingOnTransitionPlugin()
    inst = _instance_with(plugin)
    trace = inst.run_user_text("hello")
    assert plugin.calls > 0
    _assert_gov_plugin_error(inst, trace, needle="boom in on_transition")
    assert not any(t.ingress.__class__.__name__ == "EngineIoReturn" for t in trace.steps)


def test_evaluate_egress_exception_moves_gov_to_error() -> None:
    plugin = _RaisingEvaluateEgressPlugin()
    inst = _instance_with(plugin)
    trace = inst.run_user_text("hello")
    _assert_gov_plugin_error(inst, trace, needle="boom in evaluate_egress")
    assert not any(t.ingress.__class__.__name__ == "EngineIoReturn" for t in trace.steps)


def test_evaluate_ingress_exception_moves_gov_to_error() -> None:
    @dataclass
    class _BoomIngress:
        plugin_id: str = "boom-ingress"

        def evaluate_ingress(self, intent, *, config):
            raise RuntimeError("boom in evaluate_ingress")

    engine = SimulatedEngine(
        script={1: EngineIoReturn(correlation_id=1, response_kind="MODEL_TEXT", next_step="STOP", text="ok")}
    )
    inst = RuntimeInstance.from_parts(
        engine=engine,
        config=KernelConfig(
            egress_governance_plugin=_RecordingGovPlugin(),
            ingress_governance_plugins=(RegisteredIngressPlugin(plugin=_BoomIngress()),),
        ),
    )
    inst.capture_session_baseline()
    trace = inst.run_user_text("hello")
    _assert_gov_plugin_error(inst, trace, needle="boom in evaluate_ingress")
    assert not trace.client_responses


def test_observer_exception_after_allow_does_not_dispatch_engine_io() -> None:
    plugin = _RaisingOnEngineEgressPlugin()
    inst = _instance_with(plugin)
    trace = inst.run_user_text("hello")
    _assert_gov_plugin_error(inst, trace, needle="boom on egress observe")
    assert inst.kernel.q.model == ModelState.ERROR
    assert pending_for_validate(inst.kernel.q) == []
    assert not any(t.ingress.__class__.__name__ == "EngineIoReturn" for t in trace.steps)
    assert not trace.client_responses


def test_session_id_and_task_id_are_populated_and_consistent_within_one_turn() -> None:
    plugin = _RecordingGovPlugin()
    inst = _instance_with(plugin)
    inst.run_user_text("hello", session_id="fixed-session")

    assert plugin.seen, "expected at least one transition"
    session_ids = {t.session_id for t in plugin.seen}
    task_ids = {t.task_id for t in plugin.seen}
    assert session_ids == {"fixed-session"}
    assert len(task_ids) == 1
    assert next(iter(task_ids))  # non-empty


def test_task_id_changes_across_turns_session_id_does_not_when_reused() -> None:
    plugin = _RecordingGovPlugin()
    inst = _instance_with(plugin)

    inst.run_user_text("first", turn_id="u1", session_id="fixed-session")
    first_task_ids = {t.task_id for t in plugin.seen}
    plugin.seen.clear()

    inst.run_user_text("second", turn_id="u2", session_id="fixed-session")
    second_task_ids = {t.task_id for t in plugin.seen}

    assert first_task_ids != second_task_ids
    assert all(t.session_id == "fixed-session" for t in plugin.seen)
