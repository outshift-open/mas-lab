#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability operator — records boundary crossings for 3As verification."""

from __future__ import annotations

import logging
import queue
import threading
import uuid
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

_logger = logging.getLogger(__name__)


@dataclass
class ObservabilityOperator:
    """M_obs — append-only event log with attribution metadata."""

    events: list[ObservabilityEvent] = field(default_factory=list)
    _seq: int = 0
    _agent_id: str = "agent"
    _run_id: str = ""
    _subscribers: list = field(default_factory=list)
    _call_stack: list[str] = field(default_factory=list)
    _interval_call_ids: dict[tuple[int, str], str] = field(default_factory=dict)
    _call_parents: dict[str, str | None] = field(default_factory=dict)
    _async_plugins: bool = False
    _plugin_queue: queue.Queue | None = field(default=None, repr=False)
    _plugin_worker: threading.Thread | None = field(default=None, repr=False)

    def subscribe(self, plugin: object) -> None:
        """Register read-mode ObservabilityPlugin (or compatible listener)."""
        if plugin not in self._subscribers:
            self._subscribers.append(plugin)

    def set_context(self, *, agent_id: str | None = None, run_id: str | None = None) -> None:
        if agent_id is not None:
            self._agent_id = agent_id
        if run_id is not None:
            self._run_id = run_id

    def push_call_frame(self, call_id: str) -> None:
        """Push an open execution frame (e.g. agent turn) for parent_call_id attribution."""
        if call_id:
            self._call_stack.append(call_id)

    def pop_call_frame(self, call_id: str | None = None) -> None:
        """Pop the innermost frame, or the named frame if provided."""
        if not self._call_stack:
            return
        if call_id is None:
            self._call_stack.pop()
            return
        if self._call_stack[-1] == call_id:
            self._call_stack.pop()
            return
        if call_id in self._call_stack:
            self._call_stack.remove(call_id)

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
        tool_arguments: dict | None = None,
    ) -> ObservabilityEvent:
        machine = "M_tool" if op == "TOOL_CALL" else "M_model"
        resolved_tool = str(tool_name or "").strip()
        if not resolved_tool and op == "TOOL_CALL":
            resolved_tool = "tool"
        payload: dict = {
            "op": op,
            "destructive": destructive,
            "tool_name": resolved_tool,
            "envelope": True,
        }
        if tool_arguments:
            payload["tool_arguments"] = dict(tool_arguments)
        return self._emit(
            ObsEventKind.ENGINE_IO,
            ObsPhase.EXECUTE,
            machine,
            correlation_id=correlation_id,
            payload=payload,
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

    def record_session(self, session_kind: str, **fields: object) -> None:
        """Session-level transition (mas_call, execution, …) → export plugins."""
        from mas.runtime.boundary.obs.transition import TransitionEvent

        self._dispatch_transition(
            TransitionEvent(
                contract_id="orchestrator",
                mealy_symbol=session_kind,
                phase="event",
                agent_id=self._agent_id,
                run_id=self._run_id,
                attributes={k: v for k, v in fields.items()},
                boundary_kind="session",
            )
        )

    def record_parallel_group(
        self,
        *,
        boundary: str,
        group_id: str,
        tools: list[dict],
        correlation_id: int = 0,
    ) -> ObservabilityEvent:
        """Parallel tool fork/join — T-09 trajectory boundary."""
        return self._emit(
            ObsEventKind.ENVELOPE_ACTIVITY,
            ObsPhase.EXECUTE,
            "M_obs",
            correlation_id=correlation_id,
            payload={
                "activity": "parallel_group",
                "boundary": boundary,
                "group_id": group_id,
                "tools": list(tools),
                "tool_count": len(tools),
            },
        )

    def enable_async_plugins(self) -> None:
        """Dispatch export plugins on a background worker (core never waits)."""
        self._async_plugins = True

    def _ensure_plugin_worker(self) -> None:
        if self._plugin_queue is None:
            self._plugin_queue = queue.Queue()
        if self._plugin_worker is not None and self._plugin_worker.is_alive():
            return
        self._plugin_worker = threading.Thread(
            target=self._plugin_worker_loop,
            name="obs-plugin-worker",
            daemon=True,
        )
        self._plugin_worker.start()

    def _plugin_worker_loop(self) -> None:
        assert self._plugin_queue is not None
        while True:
            transition = self._plugin_queue.get()
            try:
                if transition is None:
                    return
                self._invoke_plugins(transition)
            finally:
                self._plugin_queue.task_done()

    def _invoke_plugins(self, transition) -> None:
        for plugin in self._subscribers:
            try:
                on_transition = getattr(plugin, "on_transition", None)
                if callable(on_transition):
                    on_transition(transition)
            except Exception:
                _logger.debug("observability plugin failed", exc_info=True)

    def _dispatch_transition(self, transition) -> None:
        if not self._subscribers:
            return
        if self._async_plugins:
            self._ensure_plugin_worker()
            assert self._plugin_queue is not None
            self._plugin_queue.put(transition)
            return
        self._invoke_plugins(transition)

    def drain_plugin_queue(self, *, timeout: float = 30.0) -> None:
        """Block until async plugin dispatch queue is empty."""
        if not self._async_plugins or self._plugin_queue is None:
            return
        self._plugin_queue.join()

    def shutdown_plugin_worker(self) -> None:
        """Stop background plugin worker (pipeline close)."""
        if self._plugin_queue is None:
            return
        self.drain_plugin_queue()
        self._plugin_queue.put(None)
        if self._plugin_worker is not None:
            self._plugin_worker.join(timeout=5.0)
            self._plugin_worker = None

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
        self._notify_subscribers(ev)
        return ev

    def _interval_call_id(self, correlation_id: int, op: str) -> str:
        key = (correlation_id, op)
        if key not in self._interval_call_ids:
            self._interval_call_ids[key] = str(uuid.uuid4())
        return self._interval_call_ids[key]

    def _resolve_transition_ids(self, ev: ObservabilityEvent) -> tuple[str | None, str | None]:
        """Return (call_id, parent_call_id) using envelope call stack."""
        payload = ev.payload or {}
        op = str(payload.get("op") or "")
        cid = ev.correlation_id
        parent: str | None = None

        if ev.kind == ObsEventKind.ENGINE_IO and op:
            call_id = self._interval_call_id(cid, op)
            parent = self._call_stack[-1] if self._call_stack else None
            self._call_parents[call_id] = parent
            self._call_stack.append(call_id)
            return call_id, parent

        if ev.kind == ObsEventKind.ENGINE_IO_RETURN and op:
            call_id = self._interval_call_ids.get((cid, op), f"call-{cid}" if cid else None)
            parent = self._call_parents.get(call_id) if call_id else None
            if call_id and self._call_stack and self._call_stack[-1] == call_id:
                self._call_stack.pop()
            return call_id, parent

        if ev.kind == ObsEventKind.ENVELOPE_ACTIVITY:
            activity = str(payload.get("activity") or "")
            boundary = str(payload.get("boundary") or "")
            if activity == "contract_call" and boundary == "start" and op:
                call_id = self._interval_call_id(cid, op)
                parent = self._call_stack[-1] if self._call_stack else None
                self._call_parents[call_id] = parent
                self._call_stack.append(call_id)
                return call_id, parent
            if activity == "contract_call" and boundary == "end" and op:
                call_id = self._interval_call_ids.get((cid, op))
                parent = self._call_parents.get(call_id) if call_id else None
                if call_id and self._call_stack and self._call_stack[-1] == call_id:
                    self._call_stack.pop()
                return call_id, parent

        if cid and op:
            if op == "TOOL_CALL":
                prefix = "tool"
            elif op == "MEMORY_OP":
                prefix = "memory"
            else:
                prefix = "llm"
            return f"{prefix}-{cid}", parent
        if cid:
            return f"call-{cid}", parent
        return None, parent

    def _notify_subscribers(self, ev: ObservabilityEvent) -> None:
        if not self._subscribers:
            return
        from mas.runtime.boundary.obs.transition import boundary_event_to_transition

        call_id, parent_call_id = self._resolve_transition_ids(ev)
        self._dispatch_transition(
            boundary_event_to_transition(
                ev,
                agent_id=self._agent_id,
                run_id=self._run_id,
                call_id=call_id,
                parent_call_id=parent_call_id,
            )
        )
