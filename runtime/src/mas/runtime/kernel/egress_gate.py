#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governed egress dispatch — mirrors TLA EgressAction / GovernanceEgress* actions."""

from __future__ import annotations

from mas.runtime.boundary.gov.policy import EgressIntentView, apply_egress_modify
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.envelope import (
    EnvelopeContext,
    contract_kind_for_op,
    run_egress_authorize_envelope,
)
from mas.runtime.boundary.gov.telemetry import get_bound_observability
from mas.runtime.kernel.coupling import (
    GovDecision,
    apply_control_engine_allow,
    apply_control_tool_request,
    apply_gov_block,
    apply_gov_terminate,
    enter_egress_chokepoint,
)
from mas.runtime.kernel.inflight import register_inflight
from mas.runtime.kernel.control_pipeline import control_on_idle
from mas.runtime.kernel.coord_hook import (
    coord_after_egress_allowed,
    coord_before_egress,
    coord_on_egress_blocked,
    coord_on_egress_hitl,
)
from mas.runtime.schema.egress import (
    EgressSymbol,
    InvokeEngineIo,
    NoOp,
    RaiseBoundaryError,
)
from mas.runtime.schema.governance import GovernanceAction
from mas.runtime.schema.hitl import HitlQuestionType, HitlResolveChoice
from mas.runtime.kernel.hitl_gate import emit_egress_hitl_pause
from mas.runtime.machines.context import ctx_on_abort
from mas.runtime.machines.memory import memory_on_egress_start
from mas.runtime.machines.model import model_on_abort, model_on_egress
from mas.runtime.machines.tool import tool_on_abort, tool_on_egress
from mas.runtime.machines.transport import transport_on_egress
from mas.runtime.kernel.state import (
    DpState,
    QProduct,
    ScheduledEgress,
    RunLedger,
    RunEvent,
)


def _destructive_for_op(op: ScheduledEgress, config: KernelConfig) -> bool:
    if op != "TOOL_CALL":
        return False
    return config.gov_trigger_destructive


def _append_synthetic_skip(q: QProduct, run: RunLedger) -> None:
    cid = run.next_correlation_id()
    run.append(
        RunEvent(correlation_id=cid, response_kind="TOOL_RESULT", next_step="STOP")
    )
    q.model = model_on_abort(q.model)
    q.tool = tool_on_abort(q.tool)
    q.inflight_kind = "NONE"
    q.dp = DpState.EVALUATING
    control_on_idle(q)


def _apply_engine_allow(q: QProduct, view: EgressIntentView) -> None:
    """Peer posture after gov ALLOW — coupling patch + local M_tool/M_model δ only."""
    apply_control_engine_allow(q, op=view.op)  # type: ignore[arg-type]
    if view.op == "LLM_CALL":
        q.model = model_on_egress(q.model, view.op)
    elif view.op == "TOOL_CALL":
        q.tool = tool_on_egress(q.tool, view.op)
    elif view.op == "MEMORY_OP":
        q.memory = memory_on_egress_start(q.memory, view.op)
    elif view.op == "TRANSPORT_MSG":
        q.transport = transport_on_egress(q.transport, view.op)


def schedule_tool_egress(
    q: QProduct, run: RunLedger, config: KernelConfig
) -> list[EgressSymbol]:
    """Agentic ACT → control REQUEST; run egress governance / HITL at chokepoint."""
    apply_control_tool_request(q)
    return emit_scheduled_egress(q, run, config)


def _envelope_context(
    q: QProduct,
    *,
    config: KernelConfig,
    op: ScheduledEgress,
    cid: int,
    destructive: bool,
    hitl_override: bool,
) -> EnvelopeContext:
    return EnvelopeContext(
        q=q,
        correlation_id=cid,
        contract=contract_kind_for_op(op),
        scheduled_op=op,
        observability=get_bound_observability(),
        config=config,
        tool_name=q.pending_tool_name,
        tool_arguments=dict(q.pending_tool_args or {}),
        destructive=destructive,
        hitl_gov_override=hitl_override,
    )


def emit_scheduled_egress(
    q: QProduct, run: RunLedger, config: KernelConfig
) -> list[EgressSymbol]:
    if q.scheduled_egress == "NONE":
        return [NoOp()]
    if q.tool_blacklisted and q.scheduled_egress == "TOOL_CALL":
        q.scheduled_egress = "NONE"
        _append_synthetic_skip(q, run)
        return [NoOp()]

    op = q.scheduled_egress
    if op == "TOOL_CALL" and q.hitl_block_committed:
        q.scheduled_egress = "NONE"
        cid = run.next_correlation_id()
        run.append(
            RunEvent(
                correlation_id=cid,
                response_kind="TOOL_RESULT",
                next_step="STOP",
                text="Tool call suppressed after operator HITL block.",
            )
        )
        q.model = model_on_abort(q.model)
        q.tool = tool_on_abort(q.tool)
        q.inflight_kind = "NONE"
        q.dp = DpState.EVALUATING
        control_on_idle(q)
        return [NoOp()]

    enter_egress_chokepoint(q)
    coord_before_egress(q)
    cid = run.allocate_correlation_id()
    destructive = _destructive_for_op(op, config)
    hitl_override = bool(
        q.hitl_gov_override
        or (config.hitl_once_per_turn and q.hitl_tools_approved_turn and op == "TOOL_CALL")
    )
    env_ctx = _envelope_context(
        q,
        config=config,
        op=op,
        cid=cid,
        destructive=destructive,
        hitl_override=hitl_override,
    )
    decision = run_egress_authorize_envelope(env_ctx)

    view = EgressIntentView(
        op=op,
        destructive=destructive,
        correlation_id=cid,
        tool_name=q.pending_tool_name,
        tool_arguments=q.pending_tool_args,
    )

    if decision == GovDecision.HITL:
        if op == "TOOL_CALL":
            return emit_egress_hitl_pause(
                q,
                cid=cid,
                op=op,
                question="Approve tool call?",
                question_type=HitlQuestionType.CONFIRM,
                offered_actions=[
                    HitlResolveChoice.ALLOW,
                    HitlResolveChoice.BLOCK,
                    HitlResolveChoice.SKIP,
                ],
                context_data={
                    "op": op,
                    "tool": q.pending_tool_name,
                    "arguments": q.pending_tool_args or {},
                },
            )
        return emit_egress_hitl_pause(
            q,
            cid=cid,
            op=op,
            question=f"Approve {op}?",
            question_type=HitlQuestionType.MULTIPLE_CHOICE,
            offered_actions=[
                HitlResolveChoice.ALLOW,
                HitlResolveChoice.BLOCK,
                HitlResolveChoice.TERMINATE,
            ],
            context_data={"op": op, "destructive": destructive},
        )

    if decision == GovDecision.BLOCK:
        apply_gov_block(q)
        coord_on_egress_blocked(q)
        return [RaiseBoundaryError(code="GOV_BLOCK", recoverable=True)]

    if decision == GovDecision.TERMINATE:
        apply_gov_terminate(q)
        return [RaiseBoundaryError(code="GOV_TERMINATE", recoverable=False)]

    if decision in {GovDecision.SKIP, GovDecision.BLACKLIST}:
        if decision == GovDecision.BLACKLIST:
            q.tool_blacklisted = True
        q.scheduled_egress = "NONE"
        _append_synthetic_skip(q, run)
        return [NoOp()]

    if decision == GovDecision.RETRY:
        if q.gov_retry_count >= config.max_gov_retries:
            apply_gov_block(q)
            return [RaiseBoundaryError(code="GOV_RETRY_EXHAUSTED", recoverable=True)]
        q.gov_retry_count += 1
        q.dp = DpState.EGRESS_PENDING
        return [NoOp()]

    view = apply_egress_modify(view, GovernanceAction(decision.value))
    q.hitl_gov_override = False
    _apply_engine_allow(q, view)
    register_inflight(q, cid)
    q.pending_engine_correlation_id = cid
    coord_after_egress_allowed(q)

    out: list[EgressSymbol] = [
        InvokeEngineIo(correlation_id=cid, op=view.op, destructive=view.destructive)  # type: ignore[arg-type]
    ]
    if decision == GovDecision.LOG:
        out.append(NoOp())
    return out
