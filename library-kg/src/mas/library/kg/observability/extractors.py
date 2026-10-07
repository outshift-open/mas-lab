"""Pure extractor functions for OTel span fields.

All functions are stateless (no I/O, no side effects).  They operate on raw
span dicts from either the ioa_observe / MAS SDK format or the OpenClaw
ClickHouse format, and use vocabulary.py constants instead of inline strings.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from mas.library.kg.exceptions import OtelSchemaError
from mas.library.kg.observability.helpers import ns_to_s
from mas.library.kg.observability.vocabulary import (
    GenAIAttrs,
    IoaObserveAttrs,
    MasBoundaryAttrs,
)

# ---------------------------------------------------------------------------
# Generic attribute normalisation
# ---------------------------------------------------------------------------

def normalize_attrs(span: Any) -> Dict[str, Any]:
    """Return a flat attribute dict regardless of SDK serialisation format.

    Handles:
    - Plain ``{"attributes": {key: value}}`` (Python SDK default)
    - OTel SDK ``to_json()`` list format: ``[{"key": ..., "value": {...}}]``
    """
    if span is None:
        return {}
    if isinstance(span, str):
        try:
            loaded = json.loads(span)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    if isinstance(span, dict) and "attributes" not in span:
        return span

    raw = span.get("attributes", {}) if isinstance(span, dict) else {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        out: Dict[str, Any] = {}
        for entry in raw:
            k = entry.get("key", "")
            v_obj = entry.get("value", {})
            if "stringValue" in v_obj:
                out[k] = v_obj["stringValue"]
            elif "intValue" in v_obj:
                out[k] = int(v_obj["intValue"])
            elif "doubleValue" in v_obj:
                out[k] = float(v_obj["doubleValue"])
            elif "boolValue" in v_obj:
                out[k] = bool(v_obj["boolValue"])
            else:
                out[k] = str(v_obj)
        return out
    return {}


def link_attrs(link: Dict[str, Any]) -> Dict[str, Any]:
    """Return flattened attribute dict from a span Link object."""
    return normalize_attrs({"attributes": link.get("attributes", {})})


# ---------------------------------------------------------------------------
# Stable / deterministic ID generation
# ---------------------------------------------------------------------------

def stable_id(namespace: str, run_id: Optional[str] = None, key: Optional[str] = None) -> str:
    """Deterministic UUID5 hex ID — idempotent across re-processing."""
    if key is None:
        if run_id is None:
            raise TypeError("stable_id requires either (namespace, run_id, key) or (run_id, key)")
        run_id, key = namespace, run_id
        namespace = "otel"
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{namespace}|{run_id}|{key}").hex


# ---------------------------------------------------------------------------
# Timestamp conversion
# ---------------------------------------------------------------------------


def otel_ts_to_epoch(ts: Any, span_id: str = "", field: str = "Timestamp") -> float:
    """Convert an OTel timestamp to Unix epoch seconds (float).

    Accepts:
    - Nanosecond integer or numeric string
    - ISO-8601 string (e.g. ``"2026-04-09T13:54:57.823Z"``)

    Raises
    ------
    OtelSchemaError
        When the value is absent or cannot be parsed.
    """
    if ts is None:
        return 0.0
    if ts == "":
        raise OtelSchemaError(span_id or "unknown", field, "Empty or missing timestamp")
    if isinstance(ts, (int, float)) and ts < 1e12:
        return float(ts)
    try:
        return int(ts) / 1e9
    except (ValueError, TypeError):
        pass
    try:
        cleaned = str(ts).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).timestamp()
    except (ValueError, TypeError):
        raise OtelSchemaError(span_id or "unknown", field, f"Cannot parse timestamp: {ts!r}")


# ---------------------------------------------------------------------------
# ioa_observe span field readers
# ---------------------------------------------------------------------------


def ioa_span_id(span: Dict[str, Any]) -> str:
    """Return the span_id from context or top-level."""
    raw = span.get("context", {}).get("span_id") or span.get("span_id") or ""
    if isinstance(raw, int):
        return format(raw, "016x")
    return str(raw)


def ioa_trace_id(span: Dict[str, Any]) -> str:
    """Return the trace_id from context or top-level."""
    raw = span.get("context", {}).get("trace_id") or span.get("trace_id") or ""
    if isinstance(raw, int):
        return format(raw, "032x")
    return str(raw)


def ioa_parent_id(span: Dict[str, Any]) -> Optional[str]:
    """Return parent span_id, or None if this is a root span."""
    ctx = span.get("parent") or span.get("parent_id")
    if not ctx:
        return None
    if isinstance(ctx, int):
        return format(ctx, "016x")
    if isinstance(ctx, dict):
        raw = ctx.get("span_id", "")
        return format(int(raw), "016x") if isinstance(raw, int) else str(raw)
    return str(ctx)


def _parse_span_edge_timestamp(raw: Any, sid: str, field: str, alt_field: str) -> float:
    """Shared parser for ``ioa_t_start``/``ioa_t_end``: nanosecond int/numeric
    string, or ISO-8601 string, to epoch seconds (float)."""
    if raw is None:
        raise OtelSchemaError(sid, field, f"Missing {field} / {alt_field}")
    if isinstance(raw, str):
        try:
            return ns_to_s(int(raw))
        except ValueError:
            pass
        # Try ISO-8601
        try:
            cleaned = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned).timestamp()
        except (ValueError, TypeError):
            raise OtelSchemaError(sid, field, f"Cannot parse timestamp: {raw!r}")
    return ns_to_s(int(raw))


def ioa_t_start(span: Dict[str, Any], sid: str = "") -> float:
    """Return span start time in seconds (epoch float)."""
    raw = span.get("start_time") or span.get("startTimeUnixNano")
    return _parse_span_edge_timestamp(raw, sid, "start_time", "startTimeUnixNano")


def ioa_t_end(span: Dict[str, Any], sid: str = "") -> float:
    """Return span end time in seconds (epoch float)."""
    raw = span.get("end_time") or span.get("endTimeUnixNano")
    return _parse_span_edge_timestamp(raw, sid, "end_time", "endTimeUnixNano")


def ioa_duration_ms(span: Dict[str, Any], sid: str = "") -> float:
    """Return span duration in milliseconds."""
    return (ioa_t_end(span, sid) - ioa_t_start(span, sid)) * 1000.0


def ioa_span_name(span: Dict[str, Any]) -> str:
    """Return span name from either 'name' or 'span_name' field."""
    return span.get("name") or span.get("span_name") or ""


def ioa_status_ok(span: Dict[str, Any]) -> bool:
    """Return True when the span status is not an error."""
    status = span.get("status", {})
    if isinstance(status, dict):
        return status.get("status_code", "ok").lower() not in {"error", "unset"}
    return True


# ---------------------------------------------------------------------------
# Semantic attribute readers
# ---------------------------------------------------------------------------

def ioa_span_kind(attrs: Dict[str, Any]) -> Optional[str]:
    """Return normalised ioa_observe span kind string (prefers new key)."""
    raw = attrs.get(IoaObserveAttrs.SPAN_KIND) or attrs.get(IoaObserveAttrs.SPAN_KIND_LEGACY)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).lower()


def mas_boundary(attrs: Dict[str, Any]) -> str:
    """Return the mas.boundary value, or empty string if absent."""
    return str(attrs.get(MasBoundaryAttrs.BOUNDARY, "") or "")


def is_llm_span(span_name: Any, attrs: Optional[Dict[str, Any]] = None) -> bool:
    """Return True when the span represents an LLM completion call."""
    if attrs is None and isinstance(span_name, dict):
        attrs = span_name
        span_name = ""
    attrs = attrs or {}
    span_name = str(span_name or "")

    if mas_boundary(attrs) == "LLMCall":
        return True
    kind = ioa_span_kind(attrs)
    if kind == "llm":
        return True
    op = str(attrs.get(GenAIAttrs.OPERATION, "")).lower()
    if op in {"chat", "text_completion", "completion"}:
        return True
    name_lower = span_name.lower()
    llm_verbs = {"chat", "completion", "generate", "messages", "invoke"}
    return any(v in name_lower for v in llm_verbs)


def extract_model(attrs: Dict[str, Any]) -> Optional[str]:
    """Return model name from GenAI attributes, preferring response model."""
    model = (
        attrs.get(GenAIAttrs.RESP_MODEL)
        or attrs.get(GenAIAttrs.REQ_MODEL)
        or attrs.get("mas.llm.model")
    )
    return str(model) if model else None


def extract_tokens(attrs: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """Return token counts in a backward-compatible dict form."""
    in_raw = attrs.get(GenAIAttrs.IN_TOKENS) or attrs.get("mas.llm.usage.prompt_tokens")
    out_raw = attrs.get(GenAIAttrs.OUT_TOKENS) or attrs.get("mas.llm.usage.completion_tokens")
    total_raw = attrs.get(GenAIAttrs.TOTAL_TOKENS) or attrs.get("mas.llm.usage.total_tokens")

    in_tok = int(in_raw) if in_raw not in (None, "") else None
    out_tok = int(out_raw) if out_raw not in (None, "") else None
    total_tok = int(total_raw) if total_raw not in (None, "") else None
    if total_tok is None and in_tok is not None and out_tok is not None:
        total_tok = in_tok + out_tok

    return {
        "prompt_tokens": in_tok,
        "completion_tokens": out_tok,
        "total_tokens": total_tok,
    }


def _normalize_agent_id(raw: Any) -> str:
    """Shared agent-id cleanup for ``extract_parent_agent``/``extract_agent_id``:
    strip a trailing LangGraph ``.task`` suffix, and collapse the framework's
    internal ``RunnableCallable`` sentinel (not a real agent id) to ``"unknown"``."""
    aid = str(raw or "").strip()
    if aid.endswith(".task"):
        aid = aid[:-5]
    if aid in {"RunnableCallable", "RunnableCallable.task"}:
        return "unknown"
    return aid or "unknown"


def extract_parent_agent(pid: Optional[str], by_sid: Dict[str, Any]) -> str:
    """Walk parent span to find the owning agent name."""
    if pid and pid in by_sid:
        pa = by_sid[pid]
        pa_attrs = normalize_attrs(pa)
        if ioa_span_kind(pa_attrs) == "agent" or ioa_span_name(pa).endswith(".agent"):
            return _normalize_agent_id(
                pa_attrs.get("mas.agent.id")
                or pa_attrs.get(IoaObserveAttrs.ENTITY_NAME)
                or pa_attrs.get(IoaObserveAttrs.ENTITY_NAME_LEGACY)
            )
    return "unknown"


def extract_agent_id(span_name: str, attrs: Dict[str, Any]) -> str:
    """Return agent_id from entity name attribute or span name."""
    explicit = (
        attrs.get("mas.agent.id")
        or attrs.get(IoaObserveAttrs.ENTITY_NAME)
        or attrs.get(IoaObserveAttrs.ENTITY_NAME_LEGACY)
    )
    if explicit:
        return _normalize_agent_id(explicit)
    return _normalize_agent_id(span_name.replace(".agent", ""))
