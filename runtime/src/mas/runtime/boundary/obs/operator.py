#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability operator — records boundary crossings for 3As verification."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.runtime.schema.egress import (
    EgressKind,
    EgressSymbol,
    EmitClientResponse,
    EmitHitlRequest,
    InvokeEngineIo,
    RaiseBoundaryError,
    RequestCtxAssembly,
)
from mas.runtime.schema.ingress import HitlResolve, IngressSymbol
from mas.runtime.schema.observability import AuditReport, ObsEventKind, ObservabilityEvent, ObsPhase
from mas.runtime.kernel.state import QProduct


@dataclass
class ObservabilityOperator:
    """M_obs — append-only event log with attribution metadata."""

    events: list[ObservabilityEvent] = field(default_factory=list)
    _seq: int = 0

    def record_kernel_snapshot(self, q: QProduct, *, label: str = "snapshot") -> None:
        self._emit(
            ObsEventKind.BOUNDARY_EGRESS,
            ObsPhase.REQUEST,
            "M_dp",
            payload={
                "label": label,
                "dp": q.dp.value,
                "ctrl": q.ctrl.value,
                "scheduled_egress": q.scheduled_egress,
            },
        )

    def record_ingress(self, event: IngressSymbol, q: QProduct) -> None:
        cid = getattr(event, "correlation_id", 0)
        kind = ObsEventKind.BOUNDARY_INGRESS
        phase = ObsPhase.RESULT
        machine = "execution_engine"
        attribution = ""
        if isinstance(event, HitlResolve):
            kind = ObsEventKind.HITL_RESOLVE
            phase = ObsPhase.AUTHZ
            machine = "M_gov"
            attribution = event.resolution.value
            cid = event.request_id
        self._emit(
            kind,
            phase,
            machine,
            correlation_id=cid,
            actor_id=str(event.operator_context.get("operator_id", "operator"))
            if isinstance(event, HitlResolve)
            else "engine",
            attribution_code=attribution,
            payload={
                "ingress_kind": event.kind.value,
                "product": {
                    "dp": q.dp.value,
                    "ctx": q.ctx.value,
                    "model": q.model.value,
                    "tool": q.tool.value,
                    "gov": q.gov_state,
                    "scheduled_egress": q.scheduled_egress,
                },
            },
        )

    def record_egress(self, sym: EgressSymbol, q: QProduct) -> None:
        if sym.kind == EgressKind.INVOKE_ENGINE_IO:
            assert isinstance(sym, InvokeEngineIo)
            self._emit(
                ObsEventKind.ENGINE_IO,
                ObsPhase.EXECUTE,
                "M_tool" if sym.op == "TOOL_CALL" else "M_model",
                correlation_id=sym.correlation_id,
                payload={"op": sym.op, "destructive": sym.destructive},
            )
            return
        if sym.kind == EgressKind.EMIT_HITL_REQUEST:
            assert isinstance(sym, EmitHitlRequest)
            self._emit(
                ObsEventKind.HITL_REQUEST,
                ObsPhase.AUTHZ,
                "M_gov",
                correlation_id=sym.request_id,
                policy_name=sym.context_data.get("policy_name", "scheduler"),
                payload={
                    "question": sym.question,
                    "pending_schedule": sym.pending_schedule,
                    "offered_actions": [a.value for a in sym.offered_actions],
                },
            )
            return
        if sym.kind == EgressKind.REQUEST_CTX_ASSEMBLY:
            assert isinstance(sym, RequestCtxAssembly)
            self._emit(
                ObsEventKind.CONTEXT_STEER,
                ObsPhase.INGRESS,
                "M_ctx",
                payload={
                    "collect_id": sym.collect_id,
                    "operator_context": bool(sym.operator_context),
                    "product": {
                        "dp": q.dp.value,
                        "ctx": q.ctx.value,
                    },
                },
            )
            return
        if sym.kind == EgressKind.EMIT_CLIENT_RESPONSE:
            assert isinstance(sym, EmitClientResponse)
            self._emit(
                ObsEventKind.CLIENT_RESPONSE,
                ObsPhase.END,
                "M_dp",
                payload={"finish_reason": sym.finish_reason},
            )
            return
        if sym.kind == EgressKind.RAISE_BOUNDARY_ERROR:
            assert isinstance(sym, RaiseBoundaryError)
            self._emit(
                ObsEventKind.BOUNDARY_ERROR,
                ObsPhase.AUTHZ,
                "M_gov",
                attribution_code=sym.code,
                payload={"recoverable": sym.recoverable},
            )
            return
        self._emit(
            ObsEventKind.BOUNDARY_EGRESS,
            ObsPhase.EGRESS,
            "kernel",
            payload={"egress_kind": sym.kind.value},
        )

    def audit(self) -> AuditReport:
        cids = sorted({e.correlation_id for e in self.events if e.correlation_id > 0})
        machines = sorted({e.machine_id for e in self.events})
        phases = {e.phase for e in self.events}
        required = {
            ObsPhase.REQUEST,
            ObsPhase.AUTHZ,
            ObsPhase.EXECUTE,
            ObsPhase.RESULT,
            ObsPhase.END,
        }
        gaps: list[str] = []
        missing = required - phases
        if missing:
            gaps.append(f"missing phases: {', '.join(sorted(p.value for p in missing))}")
        hitl = any(e.kind == ObsEventKind.HITL_REQUEST for e in self.events)
        resolve = any(e.kind == ObsEventKind.HITL_RESOLVE for e in self.events)
        if hitl and not resolve:
            gaps.append("HITL request without resolve — incomplete accountability chain")
        if not cids:
            gaps.append("no correlation ids — weak attribution")
        return AuditReport(
            event_count=len(self.events),
            correlation_ids=cids,
            machines_touched=machines,
            has_full_envelope=not missing,
            auditability=len(self.events) > 0 and len(cids) > 0,
            accountability=hitl == resolve or not hitl,
            attribution=all(e.machine_id for e in self.events),
            gaps=gaps,
        )

    def record_context_mutation(
        self,
        *,
        action: str,
        turn_index: int = 0,
        correlation_id: int = 0,
        role: str = "",
        call_id: str = "",
        content_preview: str = "",
        committed_count: int = 0,
        wm_count: int = 0,
    ) -> ObservabilityEvent:
        return self._emit(
            ObsEventKind.CONTEXT_MUTATION,
            ObsPhase.INGRESS,
            "M_ctx",
            correlation_id=correlation_id,
            payload={
                "action": action,
                "turn_index": turn_index,
                "role": role,
                "call_id": call_id,
                "content_preview": content_preview,
                "committed_count": committed_count,
                "wm_count": wm_count,
            },
        )

    def record_context_assembled(
        self,
        *,
        correlation_id: int,
        turn_index: int = 0,
        agent_id: str = "agent",
        messages: list | None = None,
        segments: list | None = None,
        total_tokens: int = 0,
    ) -> ObservabilityEvent:
        return self._emit(
            ObsEventKind.CONTEXT_ASSEMBLED,
            ObsPhase.EXECUTE,
            "M_ctx",
            correlation_id=correlation_id,
            payload={
                "agent_id": agent_id,
                "turn_index": turn_index,
                "messages": list(messages or []),
                "segments": list(segments or []),
                "total_tokens": total_tokens,
                "message_count": len(messages or []),
            },
        )

    def record_envelope_activity(
        self,
        *,
        symbol: str,
        activity: str,
        boundary: str,
        phase: ObsPhase,
        correlation_id: int = 0,
        machine_id: str = "M_obs",
        payload: dict | None = None,
    ) -> ObservabilityEvent:
        return self._emit(
            ObsEventKind.ENVELOPE_ACTIVITY,
            phase,
            machine_id,
            correlation_id=correlation_id,
            payload={
                "symbol": symbol,
                "activity": activity,
                "boundary": boundary,
                **(payload or {}),
            },
        )

    def record_engine_io(
        self,
        *,
        correlation_id: int,
        op: str,
        destructive: bool = False,
        tool_name: str = "",
    ) -> ObservabilityEvent:
        machine = "M_tool" if op == "TOOL_CALL" else "M_model"
        return self._emit(
            ObsEventKind.ENGINE_IO,
            ObsPhase.EXECUTE,
            machine,
            correlation_id=correlation_id,
            payload={
                "op": op,
                "destructive": destructive,
                "tool_name": tool_name,
                "envelope": True,
            },
        )

    def record_engine_io_return(
        self,
        *,
        correlation_id: int,
        op: str,
        text: str = "",
        next_step: str = "STOP",
        response_kind: str = "",
    ) -> ObservabilityEvent:
        machine = "M_tool" if op == "TOOL_CALL" else "M_model"
        return self._emit(
            ObsEventKind.ENGINE_IO_RETURN,
            ObsPhase.RESULT,
            machine,
            correlation_id=correlation_id,
            payload={
                "op": op,
                "text": text,
                "next_step": next_step,
                "response_kind": response_kind,
                "envelope": True,
            },
        )

    def record_engine_llm_return(
        self,
        *,
        correlation_id: int,
        text: str = "",
        next_step: str = "STOP",
    ) -> ObservabilityEvent:
        return self.record_engine_io_return(
            correlation_id=correlation_id,
            op="LLM_CALL",
            text=text,
            next_step=next_step,
            response_kind="MODEL_TEXT",
        )

    def record_governance_decision(
        self,
        *,
        hook: str,
        phase: str,
        decision: str = "",
        correlation_id: int = 0,
        policy_name: str = "",
        obs_phase: ObsPhase = ObsPhase.AUTHZ,
    ) -> ObservabilityEvent:
        return self._emit(
            ObsEventKind.GOVERNANCE_DECISION,
            obs_phase,
            "M_gov",
            correlation_id=correlation_id,
            policy_name=policy_name or "kernel",
            payload={
                "hook": hook,
                "checkpoint": phase,
                "decision": decision,
            },
        )

    def _emit(
        self,
        kind: ObsEventKind,
        phase: ObsPhase,
        machine_id: str,
        *,
        correlation_id: int = 0,
        policy_name: str = "",
        actor_id: str = "kernel",
        attribution_code: str = "",
        payload: dict | None = None,
    ) -> ObservabilityEvent:
        self._seq += 1
        ev = ObservabilityEvent(
            seq=self._seq,
            kind=kind,
            phase=phase,
            machine_id=machine_id,
            correlation_id=correlation_id,
            policy_name=policy_name,
            actor_id=actor_id,
            attribution_code=attribution_code,
            payload=payload or {},
        )
        self.events.append(ev)
        return ev
