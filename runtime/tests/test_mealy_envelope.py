#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for Mealy envelope composition on tool crossings."""

from __future__ import annotations

from mas.runtime.boundary.obs.operator import ObservabilityOperator
from dataclasses import replace

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.envelope import (
    EnvelopeContext,
    contract_kind_for_op,
    execute_contract_call,
    run_egress_authorize_envelope,
    run_ingress_validate_envelope,
)
from mas.runtime.kernel.state import QProduct
from mas.runtime.schema.envelope import (
    EGRESS_ENVELOPE_SYMBOLS,
    INGRESS_ENVELOPE_SYMBOLS,
    EnvelopeSymbol,
    resolve_egress_symbols,
    resolve_ingress_symbols,
)
from mas.runtime.schema.ingress import EngineIoReturn
from mas.runtime.schema.observability import ObsEventKind


def _ctx(*, op: str = "TOOL_CALL", cid: int = 1) -> EnvelopeContext:
    return EnvelopeContext(
        q=QProduct(),
        correlation_id=cid,
        contract=contract_kind_for_op(op),
        scheduled_op=op,
        observability=ObservabilityOperator(),
        config=KernelConfig(hitl_on_tool=False),
        tool_name="web-search",
        tool_arguments={"q": "test"},
    )


def test_egress_envelope_emits_all_symbols() -> None:
    ctx = _ctx()
    run_egress_authorize_envelope(ctx)
    symbols = [e.payload.get("symbol") for e in ctx.observability.events if e.kind == ObsEventKind.ENVELOPE_ACTIVITY]  # type: ignore[union-attr]
    assert symbols == [s.value for s in EGRESS_ENVELOPE_SYMBOLS]


def test_ingress_envelope_emits_all_symbols() -> None:
    ctx = _ctx()
    ctx.ingress_event = EngineIoReturn(
        correlation_id=1,
        response_kind="TOOL_RESULT",
        next_step="STOP",
        text="result",
    )
    run_ingress_validate_envelope(ctx)
    symbols = [e.payload.get("symbol") for e in ctx.observability.events if e.kind == ObsEventKind.ENVELOPE_ACTIVITY]  # type: ignore[union-attr]
    assert symbols == [s.value for s in INGRESS_ENVELOPE_SYMBOLS]


def test_governance_decisions_before_and_after() -> None:
    ctx = _ctx()
    run_egress_authorize_envelope(ctx)
    ctx.ingress_event = EngineIoReturn(
        correlation_id=1,
        response_kind="TOOL_RESULT",
        next_step="STOP",
        text="ok",
    )
    run_ingress_validate_envelope(ctx)
    gov = [e.payload for e in ctx.observability.events if e.kind == ObsEventKind.GOVERNANCE_DECISION]  # type: ignore[union-attr]
    assert len(gov) >= 4
    egress = [p for p in gov if p.get("hook") == "egress"]
    ingress = [p for p in gov if p.get("hook") == "ingress"]
    assert any(p.get("checkpoint") == "before" for p in egress)
    assert any(p.get("checkpoint") == "after" for p in egress)
    assert any(p.get("checkpoint") == "before" for p in ingress)
    assert any(p.get("checkpoint") == "after" for p in ingress)


def test_execute_contract_call_in_process() -> None:
    ctx = _ctx()
    seen: list[str] = []

    def _run() -> str:
        seen.append("execute")
        return "ok"

    result = execute_contract_call(ctx.contract, "call", ctx, execute_fn=_run)
    assert result == "ok"
    assert seen == ["execute"]
    assert any(e.kind == ObsEventKind.ENGINE_IO for e in ctx.observability.events)  # type: ignore[union-attr]


def test_envelope_works_without_governance_plugins() -> None:
    ctx = _ctx()
    ctx.config = KernelConfig(hitl_on_tool=False, gov_block_destructive=False)
    decision = run_egress_authorize_envelope(ctx)
    assert decision.value == "ALLOW"
    assert ctx.observability is not None
    assert any(e.kind == ObsEventKind.ENVELOPE_ACTIVITY for e in ctx.observability.events)


def test_contract_kind_memory_and_transport() -> None:
    assert contract_kind_for_op("MEMORY_OP").value == "memory"
    assert contract_kind_for_op("TRANSPORT_MSG").value == "transport"
    assert contract_kind_for_op("LLM_CALL").value == "model"


def test_egress_without_gov_collapses_symbols_and_skips_policy() -> None:
    ctx = _ctx()
    ctx.config = replace(
        KernelConfig(hitl_on_tool=True, gov_block_destructive=True),
        enable_governance=False,
    )
    run_egress_authorize_envelope(ctx)
    expected = resolve_egress_symbols(
        enable_governance=False,
        enable_envelope_observability=True,
    )
    symbols = [
        e.payload.get("symbol")
        for e in ctx.observability.events  # type: ignore[union-attr]
        if e.kind == ObsEventKind.ENVELOPE_ACTIVITY
    ]
    assert symbols == [s.value for s in expected]
    assert not any(
        e.kind == ObsEventKind.GOVERNANCE_DECISION for e in ctx.observability.events  # type: ignore[union-attr]
    )


def test_egress_without_obs_collapses_symbols() -> None:
    ctx = _ctx()
    ctx.config = replace(KernelConfig(hitl_on_tool=False), enable_envelope_observability=False)
    run_egress_authorize_envelope(ctx)
    expected = resolve_egress_symbols(
        enable_governance=True,
        enable_envelope_observability=False,
    )
    assert expected == (
        resolve_egress_symbols(enable_governance=True, enable_envelope_observability=False)
    )
    symbols = [
        e.payload.get("symbol")
        for e in ctx.observability.events  # type: ignore[union-attr]
        if e.kind == ObsEventKind.ENVELOPE_ACTIVITY
    ]
    assert symbols == []
    gov = [
        e.payload
        for e in ctx.observability.events  # type: ignore[union-attr]
        if e.kind == ObsEventKind.GOVERNANCE_DECISION
    ]
    assert len(gov) >= 2


def test_minimal_envelope_without_obs_or_gov() -> None:
    ctx = _ctx()
    ctx.config = replace(
        KernelConfig(hitl_on_tool=True),
        enable_governance=False,
        enable_envelope_observability=False,
    )
    run_egress_authorize_envelope(ctx)
    egress = resolve_egress_symbols(enable_governance=False, enable_envelope_observability=False)
    assert egress == (EnvelopeSymbol.CONTRACT_START,)
    symbols = [
        e.payload.get("symbol")
        for e in ctx.observability.events  # type: ignore[union-attr]
        if e.kind == ObsEventKind.ENVELOPE_ACTIVITY
    ]
    assert symbols == []
    ctx.ingress_event = EngineIoReturn(
        correlation_id=1,
        response_kind="TOOL_RESULT",
        next_step="STOP",
        text="ok",
    )
    run_ingress_validate_envelope(ctx)
    ingress = resolve_ingress_symbols(enable_governance=False, enable_envelope_observability=False)
    assert ingress == (EnvelopeSymbol.CONTRACT_END,)
