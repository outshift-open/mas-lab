#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runtime driver — closes the kernel loop with mock HITL, engine, and ctx."""

from __future__ import annotations

import json
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from mas.runtime.boundary.hitl.responders import HitlResponder
from mas.runtime.boundary.ingress_validate import validate_ingress
from mas.runtime.kernel.inflight import pending_for_validate, register_inflight
from mas.runtime.boundary.coordination.chokepoint import ChokepointCoordinator
from mas.runtime.kernel.runtime_context import runtime_binding
from mas.runtime.machines.gov import gov_is_hitl_pending
from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.engine.simulated import SimulatedEngine
from mas.runtime.engine.worker_pool import EngineWorkerPool
from mas.runtime.kernel.orchestrator import RuntimeKernel, StepResult
from mas.runtime.driver.mocks import AutoCtxAssembler
from mas.runtime.schema.egress import (
    EgressKind,
    EgressSymbol,
    EmitClientResponse,
    EmitHitlRequest,
    InvokeEngineIo,
    RaiseBoundaryError,
    RequestCtxAssembly,
)
from mas.runtime.schema.ingress import EngineIoReturn, IngressSymbol, UserInputReceived


@dataclass
class ExchangeRecord:
    """One line in the v1-style exchange log (AGENT↔LLM↔TOOL)."""

    tag: str
    text: str
    detail: str = ""
    ts_mono: float = 0.0
    ts_wall: str = ""
    engine_raw: str = ""


def _exchange_timestamp() -> tuple[float, str]:
    return (
        time.perf_counter(),
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    )


def _engine_payload_json(obj: object) -> str:
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")  # type: ignore[union-attr]
    elif isinstance(obj, dict):
        data = obj
    else:
        return str(obj)
    return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass
class DriverStep:
    ingress: IngressSymbol
    egress: list[EgressSymbol]


@dataclass
class DriverTrace:
    steps: list[DriverStep] = field(default_factory=list)
    client_responses: list[EmitClientResponse] = field(default_factory=list)
    hitl_requests: list[EmitHitlRequest] = field(default_factory=list)
    boundary_errors: list[RaiseBoundaryError] = field(default_factory=list)
    rejected_ingress: list[IngressSymbol] = field(default_factory=list)
    awaiting_hitl: bool = False
    observability_events: list = field(default_factory=list)
    exchanges: list[ExchangeRecord] = field(default_factory=list)


@dataclass
class KernelDriver:
    """Feed ingress, auto-dispatch egress to mock HITL/engine/ctx until quiescent."""

    kernel: RuntimeKernel
    hitl: HitlResponder | None = None
    engine: SimulatedEngine | None = None
    engine_pool: EngineWorkerPool | None = None
    ctx: AutoCtxAssembler | None = field(default_factory=AutoCtxAssembler)
    observability: ObservabilityOperator | None = field(default_factory=ObservabilityOperator)
    coordination: ChokepointCoordinator | None = field(default_factory=ChokepointCoordinator)
    max_auto_steps: int = 64
    agent_id: str = "agent"
    on_exchange: Callable[[ExchangeRecord], None] | None = None
    capture_engine_io: bool = False

    def __post_init__(self) -> None:
        if self.engine_pool is None and self.engine is not None:
            self.engine_pool = EngineWorkerPool(worker=self.engine.invoke)
        if self.ctx is not None and self.observability is not None:
            self.ctx.observability = self.observability

    def feed(self, event: IngressSymbol) -> DriverTrace:
        with runtime_binding(self.coordination, self.observability):
            return self._feed_bounded(event)

    def _feed_bounded(self, event: IngressSymbol) -> DriverTrace:
        trace = DriverTrace()
        queue: deque[IngressSymbol] = deque([event])
        auto_steps = 0

        while queue and auto_steps < self.max_auto_steps:
            ingress = queue.popleft()
            if not validate_ingress(
                ingress,
                last_correlation_id=(
                    self.kernel.run.records[-1].correlation_id if self.kernel.run.records else 0
                ),
                pending_correlation_id=self.kernel.q.pending_engine_correlation_id,
                inflight_correlation_ids=pending_for_validate(self.kernel.q),
            ):
                trace.rejected_ingress.append(ingress)
                continue

            if isinstance(ingress, UserInputReceived) and self.ctx is not None:
                note = getattr(self.ctx, "note_user_input", None)
                if callable(note):
                    note(ingress.text)

            result = self.kernel.transition(ingress)
            trace.steps.append(DriverStep(ingress=ingress, egress=list(result.egress)))
            self._sync_tool_result_memory(ingress)
            if self.coordination is not None:
                self.coordination.on_internal_mutation(self.kernel.q, label=ingress.kind.value)
            if self.observability is not None:
                self.observability.record_ingress(ingress, self.kernel.q)
                for sym in result.egress:
                    if self.coordination is not None:
                        if sym.kind == EgressKind.INVOKE_ENGINE_IO and isinstance(sym, InvokeEngineIo):
                            self.coordination.after_egress_allowed(self.kernel.q)
                        elif sym.kind == EgressKind.EMIT_HITL_REQUEST:
                            self.coordination.on_egress_hitl(self.kernel.q)
                    if sym.kind != EgressKind.INVOKE_ENGINE_IO:
                        self.observability.record_egress(sym, self.kernel.q)
            auto_steps += 1

            engine_ios: list[InvokeEngineIo] = []
            for sym in result.egress:
                if sym.kind == EgressKind.INVOKE_ENGINE_IO and isinstance(sym, InvokeEngineIo):
                    engine_ios.append(sym)
                else:
                    queue.extend(self._dispatch_egress(sym, trace))
            if engine_ios:
                queue.extend(self._dispatch_engine_batch(engine_ios, trace))

        trace.awaiting_hitl = gov_is_hitl_pending(self.kernel.q)
        if self.observability is not None:
            trace.observability_events = list(self.observability.events)
        return trace

    def run(self, events: list[IngressSymbol]) -> DriverTrace:
        merged = DriverTrace()
        for event in events:
            part = self.feed(event)
            merged.steps.extend(part.steps)
            merged.client_responses.extend(part.client_responses)
            merged.hitl_requests.extend(part.hitl_requests)
            merged.boundary_errors.extend(part.boundary_errors)
            merged.rejected_ingress.extend(part.rejected_ingress)
            merged.exchanges.extend(part.exchanges)
            merged.awaiting_hitl = part.awaiting_hitl
        return merged

    def _dispatch_egress(
        self, sym: EgressSymbol, trace: DriverTrace
    ) -> list[IngressSymbol]:
        if sym.kind == EgressKind.INVOKE_ENGINE_IO:
            assert isinstance(sym, InvokeEngineIo)
            return self._dispatch_engine_batch([sym], trace)

        if sym.kind == EgressKind.REQUEST_CTX_ASSEMBLY and self.ctx is not None:
            assert isinstance(sym, RequestCtxAssembly)
            if hasattr(self.ctx, "q_product"):
                self.ctx.q_product = self.kernel.q
            return [self.ctx.complete(sym)]

        if sym.kind == EgressKind.EMIT_HITL_REQUEST:
            assert isinstance(sym, EmitHitlRequest)
            trace.hitl_requests.append(sym)
            if self.hitl is not None:
                return [self.hitl.resolve(sym)]
            return []

        if sym.kind == EgressKind.EMIT_CLIENT_RESPONSE:
            assert isinstance(sym, EmitClientResponse)
            trace.client_responses.append(sym)
            return []

        if sym.kind == EgressKind.RAISE_BOUNDARY_ERROR:
            assert isinstance(sym, RaiseBoundaryError)
            trace.boundary_errors.append(sym)
            return []

        return []

    def _emit_exchange(self, trace: DriverTrace, record: ExchangeRecord) -> None:
        trace.exchanges.append(record)
        if self.on_exchange is not None:
            self.on_exchange(record)

    def _dispatch_engine_batch(
        self, ios: list[InvokeEngineIo], trace: DriverTrace
    ) -> list[IngressSymbol]:
        q = self.kernel.q
        engine = self.engine
        pool = self.engine_pool
        if pool is None and engine is None:
            return []
        direct: list[IngressSymbol] = []
        parallel_group_id: str | None = None
        if len(ios) > 1 and all(sym.op == "TOOL_CALL" for sym in ios):
            self._record_parallel_tool_calls(ios, q)
            parallel_group_id = str(uuid.uuid4())
            self._record_parallel_group_obs(
                ios, q, boundary="start", group_id=parallel_group_id
            )
        for sym in ios:
            preview = ""
            if engine is not None:
                by_cid = q.pending_tools_by_cid.get(sym.correlation_id)
                if sym.op == "TOOL_CALL" and by_cid is not None:
                    from mas.runtime.engine.exchange_preview import format_tool_invoke

                    preview = format_tool_invoke(by_cid[0], by_cid[1])
                else:
                    preview_fn = getattr(engine, "exchange_preview", None)
                    if callable(preview_fn):
                        preview = str(preview_fn(sym.op) or "")
            ts_mono, ts_wall = _exchange_timestamp()
            engine_raw = ""
            if self.capture_engine_io:
                engine_raw = _engine_payload_json(sym)
            self._emit_exchange(
                trace,
                ExchangeRecord(
                    tag=(
                        "AGENT->LLM"
                        if sym.op == "LLM_CALL"
                        else "AGENT→TOOL"
                        if sym.op == "TOOL_CALL"
                        else f"AGENT->{sym.op}"
                    ),
                    text=preview,
                    detail=f"correlation_id={sym.correlation_id} op={sym.op}",
                    ts_mono=ts_mono,
                    ts_wall=ts_wall,
                    engine_raw=engine_raw,
                ),
            )
            if sym.op == "TOOL_CALL" and engine is not None:
                by_cid = q.pending_tools_by_cid.get(sym.correlation_id)
                if by_cid is not None:
                    setter = getattr(engine, "set_tool_for_correlation", None)
                    if callable(setter):
                        setter(sym.correlation_id, by_cid[0], by_cid[1])
                    else:
                        setter = getattr(engine, "set_scheduled_tool", None)
                        if callable(setter):
                            setter(by_cid[0], by_cid[1])
                elif q.pending_tool_name:
                    setter = getattr(engine, "set_scheduled_tool", None)
                    if callable(setter):
                        setter(q.pending_tool_name, q.pending_tool_args)
            register_inflight(q, sym.correlation_id)
            from mas.runtime.boundary.gov.telemetry import get_bound_observability
            from mas.runtime.kernel.envelope import (
                EnvelopeContext,
                contract_kind_for_op,
                run_contract_execute_obs,
            )

            # q.pending_tool_name/pending_tool_args are single shared fields that
            # only ever hold the LAST tool spec set by schedule_parallel_tools_egress's
            # loop — by the time this per-sym loop runs, every sym would read the
            # same stale (name, args) unless we look each one up by its own
            # correlation_id via pending_tools_by_cid (populated per-spec in
            # parallel_tools.py). Fall back to the shared fields for the
            # single-tool-call case, where pending_tools_by_cid is never populated.
            by_cid_obs = q.pending_tools_by_cid.get(sym.correlation_id)
            obs_tool_name, obs_tool_args = (
                by_cid_obs if by_cid_obs is not None else (q.pending_tool_name, q.pending_tool_args)
            )
            env_ctx = EnvelopeContext(
                q=q,
                correlation_id=sym.correlation_id,
                contract=contract_kind_for_op(sym.op),
                scheduled_op=sym.op,
                observability=get_bound_observability() or self.observability,
                tool_name=obs_tool_name,
                tool_arguments=dict(obs_tool_args or {}),
                destructive=sym.destructive,
            )
            run_contract_execute_obs(env_ctx)
            self._record_wait_state_obs(sym, q, boundary="start")
            # Attach this op's own resolved call_id (and parent_call_id) to
            # the invocation itself (see InvokeEngineIo.call_id/parent_call_id
            # docstrings) — the observability boundary has, by the
            # CONTRACT_EXECUTE step just above, already assigned this
            # (correlation_id, op) pair its stable call_id AND resolved its
            # parent (correctly, even for a batch of true siblings — see
            # ObservabilityOperator.begin_sibling_batch). Reading both back
            # here means the engine (and, transitively, a delegate_to_* tool
            # call) always has its own real identity AND its parent's to
            # forward — a real contract field, not a closure-captured lookup
            # done later by whichever session-orchestration code happens to
            # dispatch the delegate, and not something any downstream
            # observability plugin needs to reconstruct from a call stack of
            # its own.
            if env_ctx.observability is not None:
                own_call_id = env_ctx.observability.call_id_for(sym.correlation_id, sym.op)
                if own_call_id:
                    updates: dict = {"call_id": own_call_id}
                    parent_call_id = env_ctx.observability.parent_call_id_for(own_call_id)
                    if parent_call_id:
                        updates["parent_call_id"] = parent_call_id
                    sym = sym.model_copy(update=updates)
            if pool is not None:
                pool.submit(sym)
            else:
                assert engine is not None
                ret = engine.invoke(sym)
                self._record_engine_return(trace, sym, ret)
                self._record_wait_state_obs(sym, q, boundary="end")
                direct.append(ret)
        if pool is None:
            if parallel_group_id is not None:
                self._record_parallel_group_obs(
                    ios, q, boundary="end", group_id=parallel_group_id
                )
            return direct
        results = pool.drain()
        out: list[IngressSymbol] = []
        for sym, ret in zip(ios, results, strict=True):
            self._record_engine_return(trace, sym, ret)
            self._record_wait_state_obs(sym, q, boundary="end")
            out.append(ret)
        if parallel_group_id is not None:
            self._record_parallel_group_obs(
                ios, q, boundary="end", group_id=parallel_group_id
            )
        return out

    def _record_engine_return(
        self,
        trace: DriverTrace,
        io: InvokeEngineIo,
        ret: IngressSymbol,
    ) -> None:
        from mas.runtime.schema.ingress import EngineIoReturn
        from mas.runtime.engine.exchange_preview import format_llm_response

        if not isinstance(ret, EngineIoReturn):
            return
        self._record_working_memory(io, ret)
        # The observability end-event (ENGINE_IO_RETURN) for every op — LLM,
        # tool, and memory alike — is now recorded uniformly by
        # ObsEnvelopeMachine.step() on OBSERVABILITY_POST_EXECUTE (see
        # obs_envelope.py), driven by the kernel's own ingress processing of
        # this same return. A hand-written LLM-only call used to live here;
        # keeping it would double-record llm_call_end now that the envelope
        # machine's path actually runs for every op instead of being
        # permanently shadowed.
        detail = f"correlation_id={ret.correlation_id} response_kind={ret.response_kind}"
        ts_mono, ts_wall = _exchange_timestamp()
        engine_raw = _engine_payload_json(ret) if self.capture_engine_io else ""
        if io.op == "LLM_CALL":
            body = format_llm_response(
                text=ret.text,
                next_step=ret.next_step,
                tool_name=ret.tool_name,
                tool_arguments=ret.tool_arguments,
                response_kind=ret.response_kind,
            )
            self._emit_exchange(
                trace,
                ExchangeRecord(
                    tag="LLM->AGENT",
                    text=body,
                    detail=detail,
                    ts_mono=ts_mono,
                    ts_wall=ts_wall,
                    engine_raw=engine_raw,
                ),
            )
        elif io.op == "TOOL_CALL" and ret.text:
            self._emit_exchange(
                trace,
                ExchangeRecord(
                    tag="TOOL->AGENT",
                    text=ret.text,
                    detail=detail,
                    ts_mono=ts_mono,
                    ts_wall=ts_wall,
                    engine_raw=engine_raw,
                ),
            )

    def _record_working_memory(self, io: InvokeEngineIo, ret: EngineIoReturn) -> None:
        """Append to the working_memory context source (in-turn trajectory store)."""
        ctx = self.ctx
        if ctx is None:
            return
        store = getattr(ctx, "working_memory", None)
        if store is None:
            return
        call_id = f"call_{ret.correlation_id if io.op == 'LLM_CALL' else io.correlation_id}"
        if io.op == "LLM_CALL" and ret.next_step == "PARALLEL_TOOL_CALLS":
            return
        if io.op == "LLM_CALL" and ret.next_step == "TOOL_CALL":
            store.record_assistant_tool_call(
                call_id=call_id,
                tool_name=str(ret.tool_name or "tool"),
                arguments=dict(ret.tool_arguments or {}),
            )
            from mas.runtime.boundary.context.telemetry import record_context_mutation

            if ctx is not None:
                record_context_mutation(
                    getattr(ctx, "observability", None),
                    action="wm_append",
                    turn_index=int(getattr(ctx, "turn_index", 0) or 0),
                    correlation_id=ret.correlation_id,
                    role="assistant",
                    call_id=call_id,
                    content=f"tool_call:{ret.tool_name or 'tool'}",
                    wm_count=len(store.messages),
                    committed_count=len(getattr(ctx, "committed_messages", []) or []),
                    op="LLM_CALL",
                )
        elif io.op == "LLM_CALL" and ret.next_step == "STOP" and ret.text:
            store.record_assistant_message(ret.text)
        elif io.op == "TOOL_CALL" and ret.response_kind == "TOOL_RESULT":
            pass  # defer until ingress governance commits (see _sync_tool_result_memory)

    def _sync_tool_result_memory(self, ingress: IngressSymbol) -> None:
        from mas.runtime.machines.gov import gov_is_hitl_pending
        from mas.runtime.schema.ingress import EngineIoReturn, HitlResolve

        if gov_is_hitl_pending(self.kernel.q):
            return
        ctx = self.ctx
        if ctx is None:
            return
        store = getattr(ctx, "working_memory", None)
        if store is None:
            return

        cid = 0
        text = ""
        if isinstance(ingress, EngineIoReturn) and ingress.response_kind == "TOOL_RESULT":
            cid = ingress.correlation_id
            text = ingress.text
        elif isinstance(ingress, HitlResolve):
            for row in reversed(self.kernel.run.events):
                if row.response_kind == "TOOL_RESULT":
                    cid = row.correlation_id
                    text = row.text or ""
                    break
        else:
            return

        for row in reversed(self.kernel.run.events):
            if row.response_kind == "TOOL_RESULT" and (not cid or row.correlation_id == cid):
                text = row.text or text
                cid = row.correlation_id
                break
        if not text:
            return
        open_id = getattr(store, "_open_tool_call_id", "") or ""
        call_id = open_id or (f"call_{cid}" if cid else "")
        if not call_id:
            return
        if store.messages and store.messages[-1].get("role") == "tool":
            last_cid = store.messages[-1].get("tool_call_id", "")
            if last_cid == call_id:
                return
        store.record_tool_result(call_id=call_id, content=str(text))
        from mas.runtime.boundary.context.telemetry import record_context_mutation

        record_context_mutation(
            getattr(ctx, "observability", None),
            action="wm_append",
            turn_index=int(getattr(ctx, "turn_index", 0) or 0),
            correlation_id=cid,
            role="tool",
            call_id=call_id,
            content=text,
            wm_count=len(store.messages),
            committed_count=len(getattr(ctx, "committed_messages", []) or []),
            op="TOOL_CALL",
        )

    def _record_parallel_tool_calls(self, ios: list[InvokeEngineIo], q: Any) -> None:
        ctx = self.ctx
        if ctx is None:
            return
        store = getattr(ctx, "working_memory", None)
        if store is None:
            return
        calls: list[tuple[str, str, dict]] = []
        for sym in ios:
            by_cid = q.pending_tools_by_cid.get(sym.correlation_id)
            if by_cid is None:
                continue
            name, args = by_cid
            calls.append((f"call_{sym.correlation_id}", str(name), dict(args)))
        if calls:
            store.record_assistant_tool_calls(calls)

    def _record_parallel_group_obs(
        self,
        ios: list[InvokeEngineIo],
        q: Any,
        *,
        boundary: str,
        group_id: str,
    ) -> None:
        from mas.runtime.boundary.gov.telemetry import get_bound_observability

        obs = get_bound_observability() or self.observability
        record = getattr(obs, "record_parallel_group", None)
        if not callable(record):
            return
        tools: list[dict] = []
        for sym in ios:
            by_cid = q.pending_tools_by_cid.get(sym.correlation_id)
            if by_cid is None:
                continue
            name, args = by_cid
            tool_call_id = ""
            call_id_for = getattr(obs, "call_id_for", None)
            if callable(call_id_for):
                tool_call_id = str(call_id_for(sym.correlation_id, "TOOL_CALL") or "")
            tools.append(
                {
                    "correlation_id": sym.correlation_id,
                    "call_id": tool_call_id,
                    "tool_name": name,
                    "arguments": dict(args),
                }
            )
        if not tools:
            return
        record(
            boundary=boundary,
            group_id=group_id,
            tools=tools,
            correlation_id=ios[0].correlation_id if ios else 0,
        )

    @staticmethod
    def _tool_spec_for_correlation(q: Any, correlation_id: int) -> tuple[str, dict]:
        by_cid = q.pending_tools_by_cid.get(correlation_id)
        if by_cid is not None:
            return str(by_cid[0] or ""), dict(by_cid[1] or {})
        return str(q.pending_tool_name or ""), dict(q.pending_tool_args or {})

    def _record_wait_state_obs(self, sym: InvokeEngineIo, q: Any, *, boundary: str) -> None:
        """Emit WAIT/RESUME boundary events for delegation tool calls.

        Architecture: runtime emits a native ``envelope.activity`` marker at
        wait-entry (boundary=start) and wait-exit (boundary=end), and the
        native transform maps each marker into a tiny ProcessingCall span so
        the plot can render clickable WAIT/RESUME nodes without reconstructing
        timing heuristically from overlapping tool/peer calls.
        """
        if sym.op != "TOOL_CALL":
            return
        tool_name, _tool_args = self._tool_spec_for_correlation(q, sym.correlation_id)
        if not tool_name.startswith("delegate_to_"):
            return
        from mas.runtime.boundary.gov.telemetry import get_bound_observability
        from mas.runtime.schema.observability import ObsPhase

        obs = get_bound_observability() or self.observability
        record = getattr(obs, "record_envelope_activity", None)
        if not callable(record):
            return

        role = "WAIT" if boundary == "start" else "RESUME"
        note = (
            "agent wait on tool call; tool wait on delegated reply"
            if role == "WAIT"
            else "delegated reply received; resume caller"
        )
        record(
            symbol=f"WAIT_STATE_{role}",
            activity="wait_state",
            boundary=boundary,
            phase=ObsPhase.EXECUTE,
            correlation_id=sym.correlation_id,
            machine_id="M_coord",
            payload={
                "op": "TOOL_CALL",
                "tool_name": tool_name,
                "wait_link_id": f"delegate-{sym.correlation_id}",
                "wait_role": role,
                "wait_scope": "delegation",
                "wait_note": note,
            },
        )
