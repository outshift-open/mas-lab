#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress step unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mas.runtime.boundary.gov.ingress_plugin import IngressGovDecision
from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.ingress_step import apply_engine_io_return
from mas.runtime.kernel.runtime_context import runtime_binding
from mas.runtime.kernel.state import QProduct, RunLedger
from mas.runtime.schema.egress import InvokeEngineIo, NoOp, RaiseBoundaryError
from mas.runtime.schema.envelope import INGRESS_ENVELOPE_SYMBOLS, EnvelopeSymbol
from mas.runtime.schema.governance import GovernanceAction
from mas.runtime.schema.ingress import EngineIoReturn
from mas.runtime.schema.observability import ObsEventKind


def test_apply_engine_io_return_prefers_tool_metadata_for_correlation_id():
    q = QProduct()
    q.inflight_correlation_ids = [42]
    q.pending_tool_name = "tool_a"
    q.pending_tool_args = {"from": "fallback"}
    q.pending_tools_by_cid[42] = ("tool_b", {"from": "by_cid"})

    run = RunLedger()
    event = EngineIoReturn(
        correlation_id=42,
        response_kind="TOOL_RESULT",
        next_step="STOP",
        text="done",
    )
    config = KernelConfig()

    with patch(
        "mas.runtime.kernel.ingress_step.run_ingress_validate_envelope",
        return_value=IngressGovDecision(action=GovernanceAction.ALLOW),
    ) as env_mock, patch(
        "mas.runtime.kernel.ingress_step.commit_engine_io_return",
        return_value=[NoOp()],
    ) as commit_mock:
        out = apply_engine_io_return(
            q,
            run,
            event,
            config=config,
            evaluate=MagicMock(),
        )

    env_ctx = env_mock.call_args.args[0]
    assert env_ctx.scheduled_op == "TOOL_CALL"
    assert env_ctx.tool_name == "tool_b"
    assert env_ctx.tool_arguments == {"from": "by_cid"}

    commit_mock.assert_called_once()
    assert out == [NoOp()]


def test_ingress_denied_closes_envelope() -> None:
    q = QProduct()
    q.pending_engine_correlation_id = 2
    q.pending_tool_name = "web-search"
    run = RunLedger()
    event = EngineIoReturn(
        correlation_id=1,
        response_kind="TOOL_RESULT",
        next_step="STOP",
        text="stale",
    )
    obs = ObservabilityOperator()
    config = KernelConfig()
    with runtime_binding(None, obs):
        out = apply_engine_io_return(
            q,
            run,
            event,
            config=config,
            evaluate=MagicMock(),
        )
    assert isinstance(out[0], RaiseBoundaryError)
    assert out[0].code == "INGRESS_DENIED"
    symbols = [
        e.payload.get("symbol")
        for e in obs.events
        if e.kind == ObsEventKind.ENVELOPE_ACTIVITY
    ]
    assert EnvelopeSymbol.CONTRACT_END.value in symbols
    assert symbols == [s.value for s in INGRESS_ENVELOPE_SYMBOLS]


def test_hitl_skipped_still_closes_envelope() -> None:
    q = QProduct()
    q.hitl_results_approved_turn = True
    q.pending_tool_name = "web-search"
    run = RunLedger()
    event = EngineIoReturn(
        correlation_id=1,
        response_kind="TOOL_RESULT",
        next_step="STOP",
        text="ok",
    )
    obs = ObservabilityOperator()
    config = KernelConfig(hitl_once_per_turn=True, hitl_on_tool_result=True)
    with runtime_binding(None, obs), patch(
        "mas.runtime.kernel.ingress_step.commit_engine_io_return",
        return_value=[NoOp()],
    ) as commit_mock:
        out = apply_engine_io_return(
            q,
            run,
            event,
            config=config,
            evaluate=MagicMock(),
        )
    commit_mock.assert_called_once()
    assert out == [NoOp()]
    symbols = [
        e.payload.get("symbol")
        for e in obs.events
        if e.kind == ObsEventKind.ENVELOPE_ACTIVITY
    ]
    assert EnvelopeSymbol.OBSERVABILITY_POST_EXECUTE.value in symbols
    assert EnvelopeSymbol.CONTRACT_END.value in symbols
    assert EnvelopeSymbol.GOVERNANCE_VALIDATE.value not in symbols


def test_backtrack_decision_returns_session_boundary_signal_without_committing_error():
    q = QProduct()
    q.pending_engine_correlation_id = 9
    run = RunLedger()
    event = EngineIoReturn(
        correlation_id=9,
        response_kind="ERROR",
        next_step="STOP",
        text="connection refused",
    )

    with patch(
        "mas.runtime.kernel.ingress_step.ingress_governance_valid",
        return_value=True,
    ), patch(
        "mas.runtime.kernel.ingress_step.run_ingress_validate_envelope",
        return_value=IngressGovDecision(
            action=GovernanceAction.BACKTRACK,
            message="connection refused",
        ),
    ):
        output = apply_engine_io_return(q, run, event, config=KernelConfig(), evaluate=MagicMock())

    assert isinstance(output[0], RaiseBoundaryError)
    assert output[0].code == "INGRESS_BACKTRACK"
    assert output[0].message == "connection refused"
    assert run.events == []


def test_ingress_retry_reschedules_llm_call() -> None:
    """Typed engine ERROR + error_policy.retry → kernel re-emits LLM_CALL."""
    from mas.library.standard.plugins.governance.retry_on_error import ErrorPolicy, RetryOnErrorPlugin
    from mas.runtime.boundary.gov.filter import GovTransitionFilter
    from mas.runtime.boundary.gov.ingress_chain import RegisteredIngressPlugin
    from mas.runtime.kernel.types import ModelState

    q = QProduct()
    q.pending_engine_correlation_id = 1
    q.model = ModelState.CALLING
    q.inflight_kind = "MODEL"
    run = RunLedger()
    event = EngineIoReturn(
        correlation_id=1,
        response_kind="ERROR",
        next_step="STOP",
        text="timeout",
        failure_class="transient",
        failure_code="TIMEOUT",
    )
    config = KernelConfig(
        ingress_governance_plugins=(
            RegisteredIngressPlugin(
                plugin=RetryOnErrorPlugin(
                    error_policy=ErrorPolicy(transient="retry", fatal="block"),
                ),
                filter=GovTransitionFilter(hook="ingress", response_kind=("ERROR",)),
            ),
        ),
        max_gov_retries=2,
    )
    obs = ObservabilityOperator()
    with runtime_binding(None, obs):
        out = apply_engine_io_return(
            q,
            run,
            event,
            config=config,
            evaluate=MagicMock(),
        )
    assert q.gov_retry_count == 1
    assert any(isinstance(sym, InvokeEngineIo) and sym.op == "LLM_CALL" for sym in out)
