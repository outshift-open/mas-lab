#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Apply ingress-side governance before τ append."""

from __future__ import annotations

from mas.runtime.boundary.gov.ingress_chain import evaluate_ingress_chain
from mas.runtime.boundary.ingress_validate import ingress_governance_valid
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.control_pipeline import control_on_egress_gov, control_on_result
from mas.runtime.kernel.coord_hook import coord_after_ingress, coord_before_ingress
from mas.runtime.kernel.coupling import apply_control_valid, apply_ingress_deny
from mas.runtime.kernel.egress_gate import emit_scheduled_egress
from mas.runtime.kernel.envelope import (
    EnvelopeContext,
    contract_kind_for_op,
    run_ingress_validate_envelope,
)
from mas.runtime.boundary.gov.telemetry import get_bound_observability
from mas.runtime.kernel.hitl_gate import emit_ingress_hitl_pause
from mas.runtime.kernel.inflight import dismiss_inflight, pending_for_validate
from mas.runtime.schema.egress import EgressSymbol, NoOp, RaiseBoundaryError
from mas.runtime.schema.governance import GovernanceAction
from mas.runtime.schema.ingress import EngineIoReturn
from mas.runtime.machines.context import ctx_on_cycle_reset
from mas.runtime.machines.memory import memory_on_ingress
from mas.runtime.machines.model import model_on_abort, model_on_ingress
from mas.runtime.machines.session import session_on_done
from mas.runtime.machines.tool import tool_on_abort, tool_on_ingress
from mas.runtime.machines.transport import transport_on_ingress
from mas.runtime.kernel.state import DpState, QProduct, RunLedger, RunEvent, ToolState


def _ingress_hitl_skipped(q: QProduct, config: KernelConfig, event: EngineIoReturn) -> bool:
    return bool(
        config.hitl_once_per_turn
        and q.hitl_results_approved_turn
        and event.response_kind == "TOOL_RESULT"
        and config.hitl_on_tool_result
    )


def commit_engine_io_return(
    q: QProduct,
    run: RunLedger,
    event: EngineIoReturn,
    *,
    config: KernelConfig,
    evaluate,
) -> list[EgressSymbol]:
    inflight = pending_for_validate(q)
    if event.next_step == "TOOL_CALL" and not (event.tool_name or "").strip():
        q.dp = DpState.IDLE
        return [
            RaiseBoundaryError(
                code="MISSING_TOOL_NAME",
                recoverable=False,
                message="ENGINE returned TOOL_CALL without tool_name",
            )
        ]
    run_append = run.append_inflight if inflight else run.append
    run_append(
        RunEvent(
            correlation_id=event.correlation_id,
            response_kind=event.response_kind,
            next_step=event.next_step,
            text=event.text,
        )
    )
    if event.next_step == "TOOL_CALL":
        q.pending_tool_name = event.tool_name
        q.pending_tool_args = dict(event.tool_arguments)
    if event.next_step == "PARALLEL_TOOL_CALLS":
        q.parallel_tool_batch = [
            {"tool_name": spec.tool_name, "tool_arguments": dict(spec.tool_arguments)}
            for spec in event.parallel_tools
        ]
    q.session = session_on_done(q.session)
    q.memory = memory_on_ingress(q.memory)
    q.transport = transport_on_ingress(q.transport, response_kind=event.response_kind)
    if q.model.value == "CALLING":
        q.model = model_on_ingress(q.model, response_kind=event.response_kind)
    if q.tool.value == "EXECUTING":
        q.tool = tool_on_ingress(q.tool, response_kind=event.response_kind)
    if inflight:
        dismiss_inflight(q, event.correlation_id)
        if q.inflight_correlation_ids:
            q.inflight_kind = "TOOL"
            q.dp = DpState.AWAITING_INGRESS
            return [NoOp()]
    q.inflight_kind = "NONE"
    q.pending_engine_correlation_id = 0
    q.pending_tools_by_cid.clear()
    q.dp = DpState.EVALUATING
    apply_control_valid(q)
    coord_after_ingress(q)
    return evaluate(q, run, config)


def apply_engine_io_return(
    q: QProduct,
    run: RunLedger,
    event: EngineIoReturn,
    *,
    config: KernelConfig,
    evaluate,
) -> list[EgressSymbol]:
    last_cid = run.events[-1].correlation_id if run.events else 0
    inflight = pending_for_validate(q)
    coord_before_ingress(q)
    if not ingress_governance_valid(
        event,
        last_correlation_id=last_cid,
        pending_correlation_id=q.pending_engine_correlation_id,
        inflight_correlation_ids=inflight,
    ):
        apply_ingress_deny(q)
        return [RaiseBoundaryError(code="INGRESS_DENIED", recoverable=True)]

    if _ingress_hitl_skipped(q, config, event):
        control_on_result(q)
        control_on_egress_gov(q)
        return commit_engine_io_return(q, run, event, config=config, evaluate=evaluate)

    # q.tool.value flips EXECUTING -> DONE as soon as the FIRST result of an
    # inflight batch (multiple tool calls dispatched together) is committed
    # (see tool_on_ingress, called from commit_engine_io_return below) — by
    # the time the 2nd/3rd result's own apply_engine_io_return call reads it,
    # it already reads "DONE", so this would wrongly resolve to "LLM_CALL"
    # for every result but the first. That breaks CONTRACT_END's
    # (correlation_id, op)-keyed lookup in ObservabilityOperator, silently
    # leaking those calls' frames on the call-frame stack forever (they never
    # get popped) — which then corrupts parent_call_id for every subsequent,
    # unrelated call on that stack. q.pending_tools_by_cid holds an entry per
    # correlation_id for every TOOL_CALL dispatched as part of a batch, and —
    # unlike q.tool — isn't cleared until the WHOLE batch is dismissed, so it
    # reliably answers "was THIS specific correlation_id a tool call" even
    # after an earlier sibling's ingress already moved q.tool off EXECUTING.
    is_tool_call = event.correlation_id in q.pending_tools_by_cid or q.tool.value == "EXECUTING"
    # Memory ops dispatch one at a time (no parallel-batch tracking needed the
    # way tool calls have q.pending_tools_by_cid), so q.memory's own in-flight
    # states are enough to tell a MEMORY_OP return apart from an LLM_CALL one.
    # Without this, a memory op's ingress return silently resolved to
    # "LLM_CALL", corrupting its (correlation_id, op)-keyed call_id lookup in
    # ObservabilityOperator (it would look for "MEMORY_OP" at open time but
    # "LLM_CALL" at close time — two different call_ids for the same call).
    is_memory_op = not is_tool_call and q.memory.value in ("QUERYING", "WRITING")
    scheduled_op = "TOOL_CALL" if is_tool_call else "MEMORY_OP" if is_memory_op else "LLM_CALL"
    tool_name = q.pending_tool_name
    tool_arguments = dict(q.pending_tool_args or {})
    by_cid = q.pending_tools_by_cid.get(event.correlation_id)
    if by_cid is not None:
        tool_name, tool_arguments = by_cid[0], dict(by_cid[1] or {})

    env_ctx = EnvelopeContext(
        q=q,
        correlation_id=event.correlation_id,
        contract=contract_kind_for_op(scheduled_op),
        scheduled_op=scheduled_op,
        observability=get_bound_observability(),
        config=config,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        ingress_event=event,
    )
    ingress_decision = run_ingress_validate_envelope(env_ctx)
    action = ingress_decision.action
    control_on_result(q)
    control_on_egress_gov(q)

    if action == GovernanceAction.HITL:
        cid = run.next_correlation_id()
        return emit_ingress_hitl_pause(q, cid=cid, event=event)

    if action == GovernanceAction.RETRY:
        if q.gov_retry_count >= config.max_gov_retries:
            q.dp = DpState.IDLE
            return [RaiseBoundaryError(code="INGRESS_RETRY_EXHAUSTED", recoverable=True)]
        q.gov_retry_count += 1
        q.scheduled_egress = "TOOL_CALL" if q.tool == ToolState.EXECUTING else "LLM_CALL"
        q.dp = DpState.EGRESS_PENDING
        q.inflight_kind = "NONE"
        q.model = model_on_abort(q.model) if q.model.value == "ERROR" else q.model
        q.tool = tool_on_abort(q.tool) if q.tool.value == "ERROR" else q.tool
        return emit_scheduled_egress(q, run, config)

    if action == GovernanceAction.BLOCK:
        q.dp = DpState.IDLE
        q.ctx = ctx_on_cycle_reset(q.ctx)
        q.scheduled_egress = "NONE"
        q.inflight_kind = "NONE"
        code = ingress_decision.boundary_code or "INGRESS_GOV_BLOCK"
        msg = ingress_decision.message
        recoverable = ingress_decision.recoverable
        return [
            RaiseBoundaryError(code=code, recoverable=recoverable, message=msg)
        ]

    if action == GovernanceAction.SKIP:
        cid = run.next_correlation_id()
        run.append(
            RunEvent(correlation_id=cid, response_kind="TOOL_RESULT", next_step="STOP")
        )
        q.inflight_kind = "NONE"
        q.dp = DpState.EVALUATING
        return evaluate(q, run, config)

    return commit_engine_io_return(q, run, event, config=config, evaluate=evaluate)
