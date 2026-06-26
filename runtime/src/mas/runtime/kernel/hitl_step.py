#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Apply operator HITL resolution — M_gov ingress only (HitlResolve* in TLA)."""

from __future__ import annotations

from collections.abc import Callable

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.egress_gate import emit_scheduled_egress
from mas.runtime.kernel.ingress_step import commit_engine_io_return
from mas.runtime.machines.gov import gov_clear_hitl, gov_is_hitl_pending, gov_on_hitl_schedule
from mas.runtime.machines.tool import tool_on_abort
from mas.runtime.schema.egress import EgressSymbol, NoOp
from mas.runtime.schema.hitl import HitlResolveChoice
from mas.runtime.schema.ingress import EngineIoReturn, HitlResolve
from mas.runtime.kernel.state import (
    CtxState,
    DpState,
    LifecycleState,
    ModelState,
    MemoryState,
    QProduct,
    SessionState,
    RunLedger,
    RunEvent,
    ToolState,
    TransportState,
)


def _clear_ingress_hitl(q: QProduct) -> None:
    q.hitl_pending_ingress = ""
    q.pending_ingress_return = {}
    gov_clear_hitl(q)


def _resolve_ingress_hitl(
    q: QProduct,
    run: RunLedger,
    event: HitlResolve,
    *,
    config: KernelConfig,
    evaluate: Callable,
) -> list[EgressSymbol]:
    pending = EngineIoReturn.model_validate(dict(q.pending_ingress_return))
    resolution = event.resolution
    steering = event.operator_context.get("steering") or event.operator_context.get("message")
    steer_text = steering if isinstance(steering, str) else str(steering) if steering else ""

    if resolution in {HitlResolveChoice.ALLOW, HitlResolveChoice.SCHEDULE}:
        q.hitl_results_approved_turn = True
        _clear_ingress_hitl(q)
        return commit_engine_io_return(
            q,
            run,
            pending,
            config=config,
            evaluate=evaluate,
        )

    tool_name = q.pending_tool_name or "tool"
    if resolution == HitlResolveChoice.BLOCK:
        text = f"Operator blocked tool result for '{tool_name}' via HITL."
        next_step = "LLM_CALL"
    elif resolution == HitlResolveChoice.SKIP:
        if steer_text:
            text = steer_text
        else:
            text = f"Operator skipped tool result for '{tool_name}' via HITL."
        next_step = "LLM_CALL"
    else:
        return [NoOp()]

    modified = pending.model_copy(update={"text": text, "next_step": next_step})
    _clear_ingress_hitl(q)
    return commit_engine_io_return(
        q,
        run,
        modified,
        config=config,
        evaluate=evaluate,
    )


def apply_hitl_resolve(
    q: QProduct,
    run: RunLedger,
    event: HitlResolve,
    *,
    config: KernelConfig,
    evaluate: Callable | None = None,
) -> list[EgressSymbol]:
    """Governance resolves HITL; DP stays AWAITING_INGRESS (waiting on tool chain)."""
    if not gov_is_hitl_pending(q):
        return [NoOp()]
    if event.request_id != q.hitl_request_id:
        return [NoOp()]

    if q.hitl_pending_ingress:
        if evaluate is None:
            return [NoOp()]
        return _resolve_ingress_hitl(q, run, event, config=config, evaluate=evaluate)

    resolution = event.resolution
    pending = q.hitl_pending_schedule

    if resolution in {HitlResolveChoice.ALLOW, HitlResolveChoice.SCHEDULE} and pending != "NONE":
        q.scheduled_egress = pending
        q.hitl_gov_override = True
        if pending == "TOOL_CALL":
            q.hitl_tools_approved_turn = True
        gov_clear_hitl(q)
        gov_on_hitl_schedule(q)
        return emit_scheduled_egress(q, run, config)

    if resolution == HitlResolveChoice.TERMINATE:
        q.ctrl = LifecycleState.STOPPED
        q.dp = DpState.IDLE
        q.ctx = CtxState.IDLE
        q.scheduled_egress = "NONE"
        q.inflight_kind = "NONE"
        q.model = ModelState.IDLE
        q.tool = tool_on_abort(q.tool)
        q.memory = MemoryState.IDLE
        q.transport = TransportState.IDLE
        q.session = SessionState.IDLE
        gov_clear_hitl(q)
        return [NoOp()]

    if resolution in {HitlResolveChoice.BLOCK, HitlResolveChoice.SKIP}:
        q.scheduled_egress = "NONE"
        q.inflight_kind = "NONE"
        q.tool = tool_on_abort(q.tool)
        gov_clear_hitl(q)
        steering = event.operator_context.get("steering") or event.operator_context.get("message")
        tool_name = q.pending_tool_name or "tool"
        if resolution == HitlResolveChoice.BLOCK:
            result_msg = f"Operator blocked tool '{tool_name}' via HITL."
            q.hitl_block_committed = True
        else:
            q.hitl_skip_committed = True
            if steering:
                result_msg = steering if isinstance(steering, str) else str(steering)
            else:
                result_msg = f"Operator skipped tool '{tool_name}' via HITL."
        cid = run.next_correlation_id()
        run.append(
            RunEvent(
                correlation_id=cid,
                response_kind="TOOL_RESULT",
                next_step="LLM_CALL",
                text=result_msg,
            )
        )
        q.scheduled_egress = "LLM_CALL"
        q.dp = DpState.EGRESS_PENDING
        return emit_scheduled_egress(q, run, config)

    return [NoOp()]
