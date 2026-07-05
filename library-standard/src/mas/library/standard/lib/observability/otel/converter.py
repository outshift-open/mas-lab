"""
MasOtelConverter — decoupled events.jsonl → OTel span conversion.

This module contains two things that are kept separate for reusability:

1. ``JSONLineFileSpanExporter``   — OTel SpanExporter that writes one JSON
   line per span to a local file.  No Docker, no collector required.

2. ``MasOtelConverter``           — stateful converter that maps MAS native
   event records (events.jsonl format) to OTel spans via a given tracer.

**Two modes of use:**

Live (during agent execution, via MasOtelPlugin hooks):
    The plugin builds a minimal event dict for each hook call and delegates
    to ``converter.process_event(event)``.  All span mapping logic lives
    here, not in the plugin.

Offline replay (from events.jsonl, via ``events_to_otel`` pipeline step):
    A pipeline step reads events.jsonl line by line and calls
    ``converter.process_event(event)`` for each entry.  The same converter
    code produces identical OTel spans from the same input — no LLM re-run.

    This separation means:
    - Agent runs only need the ``native`` observability plugin.
    - OTel / OTLP export is a post-processing pipeline step.
    - The same spans can be replayed to any backend (file, Jaeger, OTLP…)
      without rerunning the experiment.

**Parent-span correlation:**

The native events use ``call_id`` / ``parent_call_id`` for span correlation.
The converter maintains ``_open_spans: dict[call_id, (span, token)]`` and
uses ``parent_call_id`` to set the correct OTel parent context when opening
child spans.  This faithfully reconstructs the span tree in both live and
replay modes.

**Accurate timestamps in replay:**

``event["timestamp"]`` (float seconds since epoch) is converted to
nanoseconds and passed as ``start_time`` / ``end_time`` to the OTel SDK,
so replayed traces have the same timing as the original run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ClassVar

logger = logging.getLogger(__name__)

from mas.library.standard.lib.observability.export_layers import (
    ExportLayers,
    layer_for_kind,
    parse_export_layers,
    should_export_event,
)
from mas.library.standard.lib.observability.native.tool_name import resolve_tool_name

try:
    from opentelemetry import context as context_api
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
    from opentelemetry.sdk.trace.export import (
        SimpleSpanProcessor,
        SpanExporter,
        SpanExportResult,
    )

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment,misc]
    context_api = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# JSON-line file exporter
# ---------------------------------------------------------------------------

if OTEL_AVAILABLE:
    class JSONLineFileSpanExporter(SpanExporter):  # type: ignore[misc]
        """Writes finished spans as JSON lines to a local file.

        Each line is the output of ``ReadableSpan.to_json()`` — a complete,
        self-contained JSON object including trace_id, span_id, parent_span_id,
        attributes, events, and timing.

        The file is truncated on the first write after construction or after
        ``set_path()`` is called, preventing duplicate spans from accumulating
        across benchmark re-runs.

        Supports runtime path switching via ``set_path()`` for multi-run
        benchmarks.
        """

        def __init__(self, path: str | Path) -> None:
            self._path = Path(path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._lock = threading.Lock()
            self._needs_truncate = True

        def set_path(self, path: str | Path) -> None:
            """Switch output to a new file path (for multi-run scenarios)."""
            with self._lock:
                self._path = Path(path)
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._needs_truncate = True

        def reset(self) -> None:
            """Mark the next export to truncate the output file."""
            with self._lock:
                self._needs_truncate = True

        def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
            try:
                with self._lock:
                    mode = "w" if self._needs_truncate else "a"
                    with open(self._path, mode, encoding="utf-8") as f:
                        for span in spans:
                            f.write(span.to_json(indent=None) + "\n")
                    self._needs_truncate = False
                return SpanExportResult.SUCCESS
            except Exception:
                logger.exception("JSONLineFileSpanExporter: write failed")
                return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            pass

else:
    JSONLineFileSpanExporter = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# MasOtelConverter
# ---------------------------------------------------------------------------

class MasOtelConverter:
    """Converts MAS native event records to OTel spans.

    A single converter instance is stateful: it tracks open spans by
    ``call_id`` across multiple ``process_event()`` calls.  One converter
    instance corresponds to one agent session (or one replayed run).

    Not thread-safe: ``_open_spans`` and related maps are mutated by
    ``process_event``, ``_close``, and ``flush_open_spans`` without locking.

    Parameters
    ----------
    tracer:
        An initialised OTel ``Tracer`` (from ``provider.get_tracer(...)``).
    """

    def __init__(
        self,
        tracer: Any,
        app_name: str = "",
        export_layers: ExportLayers | None = None,
    ) -> None:
        if not OTEL_AVAILABLE:
            raise RuntimeError("opentelemetry-sdk is not installed")
        self.tracer = tracer
        self._app_name = app_name
        self._export_layers = export_layers or ExportLayers()
        self._run_id: str = ""  # updated from first event that carries run_id
        self._session_uuid: str = str(uuid.uuid4())
        # call_id → (span, context_token)
        self._open_spans: dict[str, tuple[Any, Any]] = {}
        # call_id → SpanContext for closed interval spans (point-span parent linking)
        self._closed_span_ctx: dict[str, Any] = {}
        # call_ids whose structural span already received a matching *_end
        self._closed_call_ids: set[str] = set()
        # call_id → agent_id (disambiguate shared ids across agents in one trace)
        self._call_id_agents: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Sentinel run_id values that must never become session identifiers.
    _SENTINEL_RUN_IDS: frozenset = frozenset({"local", "unknown"})

    def process_event(self, event: dict[str, Any]) -> None:
        """Dispatch a single native event record to the appropriate handler."""
        event = self._scope_event_call_ids(event)
        if not should_export_event(event, self._export_layers):
            return
        run_id = event.get("run_id") or (event.get("context") or {}).get("run_id", "")
        if run_id and run_id not in self._SENTINEL_RUN_IDS:
            self._run_id = run_id
        explicit_session_id = str(
            event.get("session_id") or (event.get("context") or {}).get("session_id") or ""
        ).strip()
        if explicit_session_id and explicit_session_id not in self._SENTINEL_RUN_IDS:
            self._session_uuid = explicit_session_id
        kind = event.get("kind", "")
        handler = self._HANDLERS.get(kind)
        if handler:
            handler(self, event)
        elif layer_for_kind(kind) == "governance":
            self._h_governance_event(event)
        elif kind.startswith("obs_wrap_gov_"):
            self._h_obs_wrap_gov(event)

    def flush_open_spans(self, *, status: str = "success") -> None:
        """End any spans still open so exporters receive them.

        Iterates a snapshot of ``_open_spans`` because ``_close`` pops entries.
        Single-threaded use only (see class docstring).
        """
        for call_id in list(self._open_spans):
            self._close(call_id, status=status)

    @classmethod
    def replay_file(
        cls,
        input_path: str | Path,
        output_path: str | Path,
        service_name: str = "agent-runtime",
        app_name: str = "",
        flush_timeout_ms: int = 5000,
        export_layers: ExportLayers | dict[str, Any] | None = None,
    ) -> int:
        """Replay an events.jsonl file and write OTel spans to *output_path*.

        Delegates to :func:`~mas.library.standard.lib.observability.otel.replay.replay_events_file`.
        Kept as a classmethod for backward compatibility.
        """
        from mas.library.standard.lib.observability.otel.replay import replay_events_file

        return replay_events_file(
            input_path,
            output_path,
            service_name=service_name,
            app_name=app_name,
            flush_timeout_ms=flush_timeout_ms,
            export_layers=export_layers,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scope_call_id(self, call_id: str | None, agent_id: str) -> str | None:
        """Disambiguate shared call ids (legacy ``u1-exec``, cross-agent reuse)."""
        if not call_id or not agent_id:
            return call_id
        cid = str(call_id)
        if cid.endswith("-exec") and not cid.startswith(f"{agent_id}-"):
            return f"{agent_id}-{cid}"
        owner = self._call_id_agents.get(cid)
        if owner and owner != agent_id:
            return f"{agent_id}-{cid}"
        self._call_id_agents[cid] = agent_id
        return cid

    def _resolve_scoped_id(self, call_id: str, agent_id: str) -> str:
        """Apply agent ownership prefix for shared legacy ids (``*-exec``)."""
        owner = self._call_id_agents.get(call_id)
        if owner:
            if call_id.endswith("-exec") and not call_id.startswith(f"{owner}-"):
                return f"{owner}-{call_id}"
            return call_id
        scoped = self._scope_call_id(call_id, agent_id)
        return scoped if scoped is not None else call_id

    def _resolve_call_id_for_close(self, call_id: str | None, agent_id: str) -> str | None:
        """Map end-event call ids to the id used when the span was opened."""
        if not call_id:
            return call_id
        return self._resolve_scoped_id(str(call_id), agent_id)

    def _scope_parent_call_id(self, parent_call_id: str | None, agent_id: str) -> str | None:
        if not parent_call_id:
            return parent_call_id
        return self._resolve_scoped_id(str(parent_call_id), agent_id)

    def _scope_event_call_ids(self, event: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(event.get("agent_id") or "")
        if not agent_id:
            return event
        scoped = dict(event)
        kind = str(scoped.get("kind") or "")
        is_end = kind.endswith("_end") or kind == "user_response"
        if scoped.get("call_id") is not None:
            if is_end:
                scoped["call_id"] = self._resolve_call_id_for_close(scoped.get("call_id"), agent_id)
            else:
                scoped["call_id"] = self._scope_call_id(scoped.get("call_id"), agent_id)
                cid = str(scoped["call_id"])
                if kind.endswith("_start") and cid in self._open_spans:
                    scoped["_duplicate_start_annotation"] = True
                elif cid in self._open_spans:
                    stable = uuid.uuid4().hex[:8]
                    scoped["call_id"] = f"{cid}-{stable}"
                    self._call_id_agents[str(scoped["call_id"])] = agent_id
        if scoped.get("parent_call_id") is not None:
            scoped["parent_call_id"] = self._scope_parent_call_id(
                scoped.get("parent_call_id"), agent_id
            )
        if (
            scoped.get("call_id")
            and scoped.get("parent_call_id")
            and str(scoped["call_id"]) == str(scoped["parent_call_id"])
        ):
            scoped["parent_call_id"] = None
        return scoped

    @staticmethod
    def _ts_ns(event: dict[str, Any]) -> int | None:
        """Convert event timestamp (float seconds) to nanoseconds int."""
        ts = event.get("timestamp")
        if ts is not None:
            return int(ts * 1_000_000_000)
        return None

    @staticmethod
    def _enc(value: Any, limit: int = 2000) -> str:
        """Encode an arbitrary value to a length-limited string."""
        if value is None:
            return ""
        try:
            text = json.dumps(value, ensure_ascii=True, default=str)
        except Exception:
            text = str(value)
        return text[:limit]

    def reset_run(self) -> None:
        """Clear per-run span state before a new benchmark run."""
        self._open_spans.clear()
        self._closed_span_ctx.clear()
        self._call_id_agents.clear()
        self._closed_call_ids.clear()
        self._run_id = ""
        self._session_uuid = str(uuid.uuid4())

    @staticmethod
    def _agent_id(ev: dict[str, Any]) -> str:
        """Extract agent_id from an event, defaulting to 'unknown'."""
        return str(ev.get("agent_id") or "unknown")

    @staticmethod
    def _require_call_id(ev: dict[str, Any]) -> str:
        """Return event call_id, generating a fresh UUID when absent."""
        return str(ev.get("call_id") or uuid.uuid4())

    @staticmethod
    def _span_context(span: Any) -> Any:
        return span.get_span_context()

    def _parent_ctx(self, parent_call_id: str | None) -> Any:
        """Return OTel context with the parent span set, or the root context."""
        if parent_call_id and parent_call_id in self._open_spans:
            parent_span, _ = self._open_spans[parent_call_id]
            return trace.set_span_in_context(parent_span)
        if parent_call_id and parent_call_id in self._closed_span_ctx:
            from opentelemetry.trace import NonRecordingSpan

            parent = NonRecordingSpan(self._closed_span_ctx[parent_call_id])
            return trace.set_span_in_context(parent)
        return context_api.Context()

    def _open(
        self,
        call_id: str,
        name: str,
        attrs: dict[str, Any],
        parent_call_id: str | None = None,
        start_ns: int | None = None,
    ) -> None:
        """Open a span and store it by call_id."""
        ctx = self._parent_ctx(parent_call_id)
        overlay: dict[str, Any] = {}
        if self._app_name:
            overlay["application_id"] = self._app_name
            overlay["session.name"] = self._app_name
            if self._session_uuid:
                overlay["session.id"] = self._session_uuid
        attrs = {**attrs, **overlay, "mas.call.id": call_id}
        kwargs: dict[str, Any] = {"context": ctx, "attributes": attrs}
        if start_ns is not None:
            kwargs["start_time"] = start_ns
        span = self.tracer.start_span(name, **kwargs)
        token = context_api.attach(trace.set_span_in_context(span))
        self._open_spans[call_id] = (span, token)

    def _close(
        self,
        call_id: str | None,
        extra_attrs: dict[str, Any] | None = None,
        status: str = "success",
        end_ns: int | None = None,
    ) -> None:
        """Close a span by call_id."""
        if not call_id or call_id not in self._open_spans:
            return
        span, token = self._open_spans.pop(call_id)
        try:
            self._closed_span_ctx[call_id] = self._span_context(span)
            self._closed_call_ids.add(str(call_id))
            span.set_attribute("mas.status", status)
            for k, v in (extra_attrs or {}).items():
                if v is not None:
                    span.set_attribute(k, v if not isinstance(v, (dict, list)) else self._enc(v))
            if end_ns is not None:
                span.end(end_time=end_ns)
            else:
                span.end()
        finally:
            try:
                context_api.detach(token)
            except Exception:
                pass

    def _point(
        self,
        name: str,
        attrs: dict[str, Any],
        parent_call_id: str | None = None,
        ts_ns: int | None = None,
        call_id: str | None = None,
    ) -> None:
        """Open and immediately close a point-in-time span."""
        span_key = str(uuid.uuid4())
        point_attrs = dict(attrs)
        if call_id:
            point_attrs["mas.call.id"] = call_id
        self._open(span_key, name, point_attrs, parent_call_id, start_ns=ts_ns)
        self._close(span_key, end_ns=ts_ns)

    # ------------------------------------------------------------------
    # Event handlers — one method per native event kind
    # ------------------------------------------------------------------

    def _h_mas_call_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "TaskCall", {
            "mas.boundary": "TaskCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.run.id": ev.get("run_id", ""),
            "mas.session.id": ev.get("session_id", ""),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_mas_call_end(self, ev: dict[str, Any]) -> None:
        self._close(ev.get("call_id"), {
            "mas.output": str(ev.get("result", ""))[:2000],
        }, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_execution_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "AgentCall", {
            "mas.boundary": "AgentCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.run.id": ev.get("run_id", ""),
            "mas.input": str(ev.get("input", ""))[:2000],
            **({} if not ev.get("dp_id") else {"mas.dp.id": ev["dp_id"]}),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_execution_end(self, ev: dict[str, Any]) -> None:
        extra: dict[str, Any] = {"mas.output": str(ev.get("output", ""))[:2000]}
        if ev.get("failure_reason"):
            extra["mas.failure.reason"] = str(ev["failure_reason"])[:500]
        if ev.get("failure_category"):
            extra["mas.failure.category"] = str(ev["failure_category"])
        self._close(ev.get("call_id"), extra,
                    status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_infrastructure_info(self, ev: dict[str, Any]) -> None:
        ts = self._ts_ns(ev)
        self._point("Worker", {
            "mas.boundary": "Worker",
            "mas.agent.id": self._agent_id(ev),
            "mas.worker.id": str(ev.get("worker_id", "")),
            "mas.worker.pid": int(ev.get("worker_pid") or 0),
            "mas.worker.durable_backend": ev.get("durable_backend", "in_memory"),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_processing_call_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "ProcessingCall", {
            "mas.boundary": "ProcessingCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.processing.name": ev.get("processing_name", ""),
            "mas.processing.type": ev.get("processing_type", ""),
            "mas.processing.segments": int(ev.get("segments") or 0),
            "mas.processing.tokens": int(ev.get("tokens") or 0),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_processing_call_end(self, ev: dict[str, Any]) -> None:
        self._close(ev.get("call_id"), status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _emit_duplicate_start_annotation(self, ev: dict[str, Any], kind: str) -> bool:
        """Mirror native KG: duplicate *_start while call open → CallAnnotation."""
        if not ev.get("_duplicate_start_annotation"):
            call_id = ev.get("call_id")
            if not call_id or call_id not in self._open_spans:
                return False
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": kind,
        }, ev.get("parent_call_id"), ts_ns=ts, call_id=ev.get("call_id"))
        return True

    def _h_llm_call_start(self, ev: dict[str, Any]) -> None:
        if self._emit_duplicate_start_annotation(ev, "llm_call_start"):
            return
        call_id = self._require_call_id(ev)
        attrs: dict[str, Any] = {
            "mas.boundary": "LLMCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.llm.model": ev.get("model") or "unknown",
            "mas.llm.messages": self._enc(ev.get("messages"), limit=4000),
        }
        if ev.get("temperature") is not None:
            attrs["mas.llm.temperature"] = float(ev["temperature"])
        if ev.get("max_tokens") is not None:
            attrs["mas.llm.max_tokens"] = int(ev["max_tokens"])
        self._open(call_id, "LLMCall", attrs, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_llm_call_end(self, ev: dict[str, Any]) -> None:
        tokens = ev.get("tokens_used") or {}
        # Extract response content (completion text)
        response = ev.get("response") or {}
        if isinstance(response, dict):
            completion = response.get("content", "")
            usage = response.get("usage") or {}
            thinking = response.get("thinking", "")
            if not tokens and usage:
                tokens = usage
        else:
            completion = str(response) if response else ""
            thinking = ""
        # Fallback: output field (normalize_events uses this)
        if not completion:
            completion = ev.get("output", "")
        extra: dict[str, Any] = {
            "mas.llm.finish_reason": ev.get("finish_reason") or "",
            "mas.llm.response": str(completion)[:2000],
        }
        if thinking:
            extra["mas.llm.thinking"] = str(thinking)[:2000]
        if isinstance(tokens, dict):
            extra["metrics.token.input"] = tokens.get("prompt_tokens")
            extra["metrics.token.output"] = tokens.get("completion_tokens")
            extra["metrics.token.total"] = tokens.get("total_tokens")
        elif tokens:
            extra["metrics.token.total"] = tokens
        call_id = ev.get("call_id")
        if call_id and call_id in self._closed_call_ids:
            return
        if call_id and call_id not in self._open_spans:
            # Orphan end (no matching start in trace) — native KG still materialises
            # an LLMCall node; synthesise a zero-width span so round-trip parity holds.
            self._open(call_id, "LLMCall", {
                "mas.boundary": "LLMCall",
                "mas.agent.id": self._agent_id(ev),
                "mas.llm.model": ev.get("model") or "unknown",
            }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))
        self._close(call_id, extra, status="success", end_ns=self._ts_ns(ev))

    def _h_tool_call_start(self, ev: dict[str, Any]) -> None:
        if self._emit_duplicate_start_annotation(ev, "tool_call_start"):
            return
        call_id = self._require_call_id(ev)
        tool_name = resolve_tool_name(ev)
        attrs: dict[str, Any] = {
            "mas.boundary": "ToolCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.tool.name": tool_name,
            "mas.tool.input": self._enc(ev.get("arguments"), limit=1000),
            "mas.tool.category": ev.get("tool_category", "data"),
        }
        if ev.get("barrier_id"):
            attrs["mas.tool.barrier_id"] = ev["barrier_id"]
        self._open(call_id, "ToolCall", attrs, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_tool_call_end(self, ev: dict[str, Any]) -> None:
        result = ev.get("result", "")
        # Preserve raw string output without re-encoding
        if isinstance(result, str):
            output = result[:1000]
        else:
            output = self._enc(result, limit=1000)
        self._close(ev.get("call_id"), {
            "mas.tool.output": output,
        }, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_workflow_transition_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "WorkflowTransition", {
            "mas.boundary": "WorkflowTransition",
            "mas.agent.id": self._agent_id(ev),
            "mas.transition.type": ev.get("transition_type", ""),
            "mas.transition.arguments": self._enc(ev.get("arguments"), limit=500),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_workflow_transition_end(self, ev: dict[str, Any]) -> None:
        self._close(ev.get("call_id"), {
            "mas.transition.result": self._enc(ev.get("result"), limit=500),
        }, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_memory_store_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "MemoryCall", {
            "mas.boundary": "MemoryCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.memory.type": ev.get("memory_type") or "episodic",
            "mas.memory.operation": "write",
            "mas.memory.input": self._enc(ev.get("data") or ev.get("content"), limit=1000),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_memory_store_end(self, ev: dict[str, Any]) -> None:
        self._close(ev.get("call_id"), status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_memory_read_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "MemoryCall", {
            "mas.boundary": "MemoryCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.memory.type": ev.get("memory_type") or "episodic",
            "mas.memory.operation": "read",
            "mas.memory.key": ev.get("key") or "",
            "mas.memory.query": ev.get("query") or "",
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_memory_read_end(self, ev: dict[str, Any]) -> None:
        result = ev.get("result", "")
        extra: dict[str, Any] = {}
        if isinstance(result, str):
            extra["mas.memory.output"] = result[:1000]
        else:
            extra["mas.memory.output"] = self._enc(result, limit=1000)
        if ev.get("result_count"):
            extra["mas.memory.result_count"] = int(ev["result_count"])
        self._close(ev.get("call_id"), extra, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_memory_retrieve_start(self, ev: dict[str, Any]) -> None:
        """memory_retrieve_start is an alias for memory_read_start."""
        self._h_memory_read_start(ev)

    def _h_memory_retrieve_end(self, ev: dict[str, Any]) -> None:
        """memory_retrieve_end is an alias for memory_read_end."""
        self._h_memory_read_end(ev)

    def _h_rag_query_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "RAGQuery", {
            "mas.boundary": "RAGQuery",
            "mas.agent.id": self._agent_id(ev),
            "mas.memory.type": "rag",
            "mas.memory.query": ev.get("query") or "",
            "mas.memory.collection": ev.get("collection") or "",
            "mas.memory.top_k": int(ev.get("top_k") or 0),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_rag_query_end(self, ev: dict[str, Any]) -> None:
        result = ev.get("result", "")
        extra: dict[str, Any] = {}
        if isinstance(result, str):
            extra["mas.memory.output"] = result[:1000]
        else:
            extra["mas.memory.output"] = self._enc(result, limit=1000)
        if ev.get("result_count"):
            extra["mas.memory.result_count"] = int(ev["result_count"])
        self._close(ev.get("call_id"), extra, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_governance_checked(self, ev: dict[str, Any]) -> None:
        """governance_checked is an alias for governance_event."""
        self._h_governance_event(ev)

    def _h_agent_communication_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "AgentCommunication", {
            "mas.boundary": "AgentCommunication",
            "mas.agent.id": self._agent_id(ev),
            "mas.communication.type": ev.get("message_type") or "",
            "mas.communication.source": ev.get("source_agent_id") or "",
            "mas.communication.target": ev.get("target_agent_id") or "",
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_agent_communication_end(self, ev: dict[str, Any]) -> None:
        self._close(ev.get("call_id"), {
            "mas.communication.correlation_id": ev.get("correlation_id") or "",
        }, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_skill_execution_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "SkillExecution", {
            "mas.boundary": "SkillExecution",
            "mas.agent.id": self._agent_id(ev),
            "mas.skill.name": ev.get("skill_name") or "",
            "mas.skill.input": self._enc(ev.get("input"), limit=1000),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_skill_execution_end(self, ev: dict[str, Any]) -> None:
        output = ev.get("output", "")
        extra: dict[str, Any] = {}
        if isinstance(output, str):
            extra["mas.skill.output"] = output[:1000]
        else:
            extra["mas.skill.output"] = self._enc(output, limit=1000)
        self._close(ev.get("call_id"), extra, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    def _h_governance_event(self, ev: dict[str, Any]) -> None:
        ts = self._ts_ns(ev)
        self._point("GovernanceEvent", {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "governance_checked"),
            "mas.governance.hook": ev.get("hook", ""),
            "mas.governance.outcome": ev.get("outcome", "allowed"),
            "mas.governance.checks_passed": int(ev.get("checks_passed") or 0),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_routing(self, ev: dict[str, Any]) -> None:
        """delegation routing event → CallAnnotation point span."""
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": "routing",
            "mas.annotation.content": json.dumps({
                "routing_type": ev.get("routing_type", ""),
                "selected_agent": ev.get("selected_agent", ""),
                "confidence": ev.get("confidence"),
                "candidates": ev.get("candidates", []),
            }),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_context_assembled(self, ev: dict[str, Any]) -> None:
        """Emit a CallAnnotation for the context_assembled event."""
        ts = self._ts_ns(ev)
        parent = ev.get("parent_call_id")
        agent_id = self._agent_id(ev)
        segments = ev.get("segments") or []
        if isinstance(segments, int):
            segment_count = segments
            total_tokens = int(ev.get("total_tokens") or 0)
        else:
            segment_count = len(segments)
            total_tokens = ev.get("total_tokens") or sum(
                int(s.get("tokens") or 0) for s in segments
            )
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": agent_id,
            "mas.annotation.kind": "context_assembled",
            "mas.annotation.content": json.dumps({
                "segments": segment_count,
                "total_tokens": total_tokens,
            }),
        }, parent, ts_ns=ts)

    def _h_context_part_contributed(self, ev: dict[str, Any]) -> None:
        """Emit a ContextContribution point span for explicit context part events."""
        ts = self._ts_ns(ev)
        parent = ev.get("parent_call_id")
        agent_id = self._agent_id(ev)
        attrs: dict[str, Any] = {
            "mas.boundary": "ContextContribution",
            "mas.agent.id": agent_id,
            "mas.context.part_id": ev.get("part_id") or ev.get("call_id", ""),
            "mas.context.source": ev.get("source", ""),
            "mas.context.section_id": ev.get("section_id", ""),
            "mas.context.source_type": ev.get("source_type", "unknown"),
            "mas.context.access_mechanism": ev.get("access_mechanism", "inject"),
            "mas.context.cause": ev.get("cause", "context_manager"),
            "mas.context.cause_type": ev.get("cause_type", "deterministic"),
            "mas.context.token_estimate": int(ev.get("token_estimate") or ev.get("tokens") or 0),
            "mas.context.retained": ev.get("retained", True),
        }
        llm_call_id = ev.get("llm_call_id") or ""
        if llm_call_id:
            attrs["mas.context.llm_call_id"] = llm_call_id
        self._point("ContextContribution", attrs, parent, ts_ns=ts)

    def _h_state_update_start(self, ev: dict[str, Any]) -> None:
        """state_update_start → CallAnnotation point span (annotation, not structural)."""
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": "state_update_start",
            "mas.annotation.content": json.dumps({
                "state_key": ev.get("state_key", ""),
                "state_value": ev.get("state_value", ""),
            }),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_state_update_end(self, ev: dict[str, Any]) -> None:
        """state_update_end → CallAnnotation point span."""
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": "state_update_end",
            "mas.annotation.content": json.dumps({
                "state_key": ev.get("state_key", ""),
                "state_value": ev.get("state_value", ""),
            }),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_governance_policy(self, ev: dict[str, Any]) -> None:
        """Handle governance_policy / transformation_event."""
        ts = self._ts_ns(ev)
        attrs: dict[str, Any] = {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "governance_policy"),
            "mas.governance.policy_name": ev.get("policy_name", ""),
            "mas.governance.trigger_point": ev.get("trigger_point", ""),
            "mas.governance.evaluation_mode": ev.get("evaluation_mode", ""),
            "mas.governance.outcome": ev.get("outcome", ""),
            "mas.governance.action_taken": ev.get("action_taken", ""),
        }
        details = ev.get("details") or {}
        if details.get("condition"):
            attrs["mas.governance.condition"] = details["condition"]
        if details.get("tool_filter"):
            attrs["mas.governance.tool_filter"] = details["tool_filter"]
        self._point("GovernanceEvent", attrs, ev.get("parent_call_id"), ts_ns=ts)

    def _h_hitl_request(self, ev: dict[str, Any]) -> None:
        """Handle hitl_request events."""
        ts = self._ts_ns(ev)
        self._point("GovernanceEvent", {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "hitl_request"),
            "mas.governance.policy_name": ev.get("policy_name", ""),
            "mas.governance.auto_approve": ev.get("auto_approve", False),
            "mas.governance.timeout_s": ev.get("timeout_s", 30.0),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_policy_event(self, ev: dict[str, Any]) -> None:
        """Handle policy_denial / policy_allow events."""
        ts = self._ts_ns(ev)
        self._point("GovernanceEvent", {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "policy_denial"),
            "mas.governance.decision_type": ev.get("decision_type", "deny"),
            "mas.governance.policy_id": ev.get("policy_id", ""),
            "mas.governance.reason": ev.get("reason", ""),
            "mas.governance.denied_call_id": ev.get("denied_call_id", ""),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_hitl_gate(self, ev: dict[str, Any]) -> None:
        """Handle hitl_gate events."""
        ts = self._ts_ns(ev)
        self._point("GovernanceEvent", {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "hitl_gate"),
            "mas.governance.decision_type": ev.get("decision_type", ""),
            "mas.governance.policy_id": ev.get("policy_id", ""),
            "mas.governance.reason": ev.get("reason", ""),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_budget_event(self, ev: dict[str, Any]) -> None:
        """Handle budget_event events."""
        ts = self._ts_ns(ev)
        self._point("GovernanceEvent", {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "budget_event"),
            "mas.governance.decision_type": ev.get("decision_type", ""),
            "mas.governance.policy_id": ev.get("policy_id", ""),
            "mas.governance.reason": ev.get("reason", ""),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_control_intervention(self, ev: dict[str, Any]) -> None:
        """Handle control_intervention events."""
        ts = self._ts_ns(ev)
        self._point("GovernanceEvent", {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "control_intervention"),
            "mas.governance.decision_type": ev.get("decision_type", ""),
            "mas.governance.policy_id": ev.get("policy_id", ""),
            "mas.governance.reason": ev.get("reason", ""),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_governance_denied(self, ev: dict[str, Any]) -> None:
        """governance_denied (emitted by contracts) → GovernanceEvent point span."""
        ts = self._ts_ns(ev)
        self._point("GovernanceEvent", {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": self._agent_id(ev),
            "mas.governance.kind": ev.get("kind", "governance_denied"),
            "mas.governance.decision_type": "deny",
            "mas.governance.policy_id": ev.get("contract_id") or ev.get("policy_id", ""),
            "mas.governance.hook": ev.get("hook", ""),
            "mas.governance.reason": ev.get("reason", "")[:500],
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_routing_result(self, ev: dict[str, Any]) -> None:
        """routing_result → CallAnnotation point span."""
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": "routing_result",
            "mas.annotation.content": json.dumps({
                "selected_agent": ev.get("selected_agent", ""),
                "target_agent_id": ev.get("target_agent_id", ""),
                "routing_type": ev.get("routing_type", ""),
            }),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_user_input(self, ev: dict[str, Any]) -> None:
        """user_input → CallAnnotation point span."""
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": "user_input",
            "mas.annotation.content": str(ev.get("content") or ev.get("input", ""))[:2000],
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_obs_wrap_gov(self, ev: dict[str, Any]) -> None:
        """obs_wrap_gov_* wrapper events → CallAnnotation point spans."""
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": ev.get("kind", "obs_wrap_gov"),
        }, ev.get("parent_call_id"), ts_ns=ts, call_id=ev.get("call_id"))

    def _h_user_output(self, ev: dict[str, Any]) -> None:
        """user_output / client_response → CallAnnotation point span."""
        ts = self._ts_ns(ev)
        ann_kind = ev.get("kind", "user_output")
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": ann_kind,
            "mas.annotation.content": str(ev.get("content") or ev.get("output", ""))[:2000],
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_compaction(self, ev: dict[str, Any]) -> None:
        """compaction → CallAnnotation point span."""
        ts = self._ts_ns(ev)
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": "compaction",
            "mas.compaction.total_messages": int(ev.get("total_messages") or 0),
            "mas.compaction.compressed_count": int(ev.get("compressed_count") or 0),
            "mas.compaction.tokens_before": int(ev.get("tokens_before") or 0),
            "mas.compaction.tokens_after": int(ev.get("tokens_after") or 0),
        }, ev.get("parent_call_id"), ts_ns=ts)

    def _h_parallel_group(self, ev: dict[str, Any]) -> None:
        """parallel_group_{start,end,merge} → CallAnnotation point span."""
        ts = self._ts_ns(ev)
        call_id = ev.get("call_id") or None
        self._point("CallAnnotation", {
            "mas.boundary": "CallAnnotation",
            "mas.agent.id": self._agent_id(ev),
            "mas.annotation.kind": ev.get("kind", "parallel_group"),
            "mas.parallel.group_id": ev.get("group_id", ""),
            "mas.parallel.phase": ev.get("phase", ""),
            "mas.parallel.agent_ids": ",".join(str(a) for a in (ev.get("agent_ids") or [])),
        }, ev.get("parent_call_id"), ts_ns=ts, call_id=call_id)

    def _h_network_call_start(self, ev: dict[str, Any]) -> None:
        call_id = self._require_call_id(ev)
        self._open(call_id, "NetworkCall", {
            "mas.boundary": "NetworkCall",
            "mas.agent.id": self._agent_id(ev),
            "mas.network.url": ev.get("url", ""),
            "mas.network.method": ev.get("method", ""),
        }, ev.get("parent_call_id"), start_ns=self._ts_ns(ev))

    def _h_network_call_end(self, ev: dict[str, Any]) -> None:
        self._close(ev.get("call_id"), {
            "mas.network.status_code": int(ev.get("status_code") or 0),
        }, status=ev.get("status", "success"), end_ns=self._ts_ns(ev))

    # ------------------------------------------------------------------
    # Dispatch table (defined after all methods)
    # ------------------------------------------------------------------

    _HANDLERS: ClassVar[dict[str, Callable[["MasOtelConverter", dict[str, Any]], None]]] = {}


# Populate dispatch table after class body (method references need the class).
MasOtelConverter._HANDLERS = {
    "mas_call_start":           MasOtelConverter._h_mas_call_start,
    "mas_call_end":             MasOtelConverter._h_mas_call_end,
    "execution_start":          MasOtelConverter._h_execution_start,
    "execution_end":            MasOtelConverter._h_execution_end,
    "infrastructure_info":      MasOtelConverter._h_infrastructure_info,
    "processing_call_start":    MasOtelConverter._h_processing_call_start,
    "processing_call_end":      MasOtelConverter._h_processing_call_end,
    "context_assembled":        MasOtelConverter._h_context_assembled,
    "context_part_contributed":  MasOtelConverter._h_context_part_contributed,
    "llm_call_start":           MasOtelConverter._h_llm_call_start,
    "llm_call_end":             MasOtelConverter._h_llm_call_end,
    "tool_call_start":          MasOtelConverter._h_tool_call_start,
    "tool_call_end":            MasOtelConverter._h_tool_call_end,
    "workflow_transition_start": MasOtelConverter._h_workflow_transition_start,
    "workflow_transition_end":  MasOtelConverter._h_workflow_transition_end,
    "memory_store_start":       MasOtelConverter._h_memory_store_start,
    "memory_store_end":         MasOtelConverter._h_memory_store_end,
    "memory_read_start":        MasOtelConverter._h_memory_read_start,
    "memory_read_end":          MasOtelConverter._h_memory_read_end,
    "memory_retrieve_start":    MasOtelConverter._h_memory_retrieve_start,
    "memory_retrieve_end":      MasOtelConverter._h_memory_retrieve_end,
    # Legacy kind names alias memory_read_* handlers.
    "memory_call_start":        MasOtelConverter._h_memory_read_start,
    "memory_call_end":          MasOtelConverter._h_memory_read_end,
    "rag_query_start":          MasOtelConverter._h_rag_query_start,
    "rag_query_end":            MasOtelConverter._h_rag_query_end,
    "agent_communication_start": MasOtelConverter._h_agent_communication_start,
    "agent_communication_end":  MasOtelConverter._h_agent_communication_end,
    "skill_execution_start":    MasOtelConverter._h_skill_execution_start,
    "skill_execution_end":      MasOtelConverter._h_skill_execution_end,
    "governance_event":         MasOtelConverter._h_governance_event,
    "governance_checked":       MasOtelConverter._h_governance_checked,
    "governance_policy":        MasOtelConverter._h_governance_policy,
    "hitl_request":             MasOtelConverter._h_hitl_request,
    "policy_denial":            MasOtelConverter._h_policy_event,
    "policy_allow":             MasOtelConverter._h_policy_event,
    "hitl_gate":                MasOtelConverter._h_hitl_gate,
    "budget_event":             MasOtelConverter._h_budget_event,
    "control_intervention":     MasOtelConverter._h_control_intervention,
    "transformation_event":     MasOtelConverter._h_governance_policy,
    "governance_denied":        MasOtelConverter._h_governance_denied,
    "routing":                  MasOtelConverter._h_routing,
    "routing_result":           MasOtelConverter._h_routing_result,
    "user_input":               MasOtelConverter._h_user_input,
    "user_output":              MasOtelConverter._h_user_output,
    "client_response":          MasOtelConverter._h_user_output,
    "compaction":               MasOtelConverter._h_compaction,
    "parallel_group_start":     MasOtelConverter._h_parallel_group,
    "parallel_group_end":       MasOtelConverter._h_parallel_group,
    "parallel_group_merge":     MasOtelConverter._h_parallel_group,
    "network_call_start":       MasOtelConverter._h_network_call_start,
    "network_call_end":         MasOtelConverter._h_network_call_end,
    "state_update_start":       MasOtelConverter._h_state_update_start,
    "state_update_end":         MasOtelConverter._h_state_update_end,
}
