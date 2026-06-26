#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Convert MAS events.jsonl (or OTel SDK spans.jsonl) to OTLP JSON and push.

Supports two input formats — detected automatically:

* **MAS custom events** (``kind``, ``timestamp``, ``run_id`` keys):
  Converted to OTel spans via :class:`~mas.library.standard.plugins.observability.otel.MasOtelConverter`
  — the single authoritative converter that handles all native event kinds.
  Requires ``opentelemetry-sdk`` (``pip install -e 'runtime[otel]'``).

* **OTel SDK spans** (``context.trace_id``, ``start_time``, ``end_time`` keys):
  Already span-shaped; fields are remapped directly to OTLP JSON.

Push target: any OTLP HTTP/JSON endpoint (e.g. ``http://localhost:4318``).
The collector endpoint must accept POST /v1/traces with Content-Type:
application/json (standard OpenTelemetry Collector HTTP receiver).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class OtlpSpan:
    """Minimal OTLP span representation (HTTP JSON schema)."""
    trace_id: str        # 32 hex chars
    span_id: str         # 16 hex chars
    name: str
    start_ns: int        # Unix nanoseconds
    end_ns: int          # Unix nanoseconds, >= start_ns
    kind: int = 1        # 0=UNSPECIFIED 1=INTERNAL 2=SERVER 3=CLIENT 4=PRODUCER 5=CONSUMER
    parent_span_id: Optional[str] = None  # 16 hex chars or None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status_code: int = 0  # 0=UNSET 1=OK 2=ERROR

    def to_otlp_dict(self) -> dict:
        span: dict = {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "name": self.name,
            "kind": self.kind,
            "startTimeUnixNano": str(self.start_ns),
            "endTimeUnixNano": str(self.end_ns),
            "attributes": _attrs_to_otlp(self.attributes),
            "status": {"code": self.status_code},
        }
        if self.parent_span_id:
            span["parentSpanId"] = self.parent_span_id
        return span


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def load_events(path: str | Path) -> list[dict]:
    """Load all non-empty JSON lines from *path*."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines if l.strip()]


def push_file(
    path: str | Path,
    endpoint: str,
    service_name: str = "mas-runtime",
    app_name: str = "",
    dry_run: bool = False,
    batch_size: int = 200,
) -> dict:
    """Convert *path* and push spans to OTLP HTTP collector at *endpoint*.

    Parameters
    ----------
    app_name:
        When non-empty, sets ``application_id`` on every span so the
        Claris/ClickHouse platform groups traces under this application name.
        Defaults to *service_name* when not provided.

    Returns a summary dict::

        {"spans": int, "batches": int, "status": "ok" | "dry-run" | "error", "detail": str}
    """
    events = load_events(path)
    if not events:
        return {"spans": 0, "batches": 0, "status": "ok", "detail": "empty file"}

    effective_app_name = app_name or service_name

    # Detect format
    first = events[0]
    if "context" in first and isinstance(first.get("context"), dict) and "trace_id" in first["context"]:
        # Already OTel SDK spans — convert directly.
        # service.name is already set on the resource by the plugin/converter;
        # only fill a fallback if the spans don't carry one.
        spans = _sdk_spans_to_otlp(events)
        resource_attrs = _resource_from_sdk(first)
        resource_attrs.setdefault("service.name", service_name)
        for s in spans:
            s.attributes["application_id"] = effective_app_name
    else:
        # MAS native events — use the authoritative MasOtelConverter.
        run_id = first.get("run_id", "unknown")
        from mas.library.standard.plugins.observability.otel.converter import (
            MasOtelConverter,
        )
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as _tmp:
            tmp_path = _tmp.name
        try:
            MasOtelConverter.replay_file(
                path, tmp_path,
                service_name=service_name,
                app_name=effective_app_name,
            )
            sdk_spans = load_events(tmp_path)
        finally:
            os.unlink(tmp_path)
        spans = _sdk_spans_to_otlp(sdk_spans)
        resource_attrs = _resource_from_sdk(sdk_spans[0]) if sdk_spans else {}
        resource_attrs.setdefault("service.name", service_name)
        resource_attrs["mas.run.id"] = run_id
        resource_attrs["mas.source"] = "mas-lab-push"

    if not spans:
        return {"spans": 0, "batches": 0, "status": "ok", "detail": "no spans generated"}

    # Build OTLP payload in batches
    url = endpoint.rstrip("/") + "/v1/traces"
    total_batches = 0
    errors: list[str] = []

    for i in range(0, len(spans), batch_size):
        chunk = spans[i : i + batch_size]
        payload = _build_otlp_payload(chunk, resource_attrs)
        total_batches += 1
        if not dry_run:
            err = _http_post_json(url, payload)
            if err:
                errors.append(err)

    status = "dry-run" if dry_run else ("error" if errors else "ok")
    detail = "; ".join(errors) if errors else f"{len(spans)} spans → {url}"
    return {"spans": len(spans), "batches": total_batches, "status": status, "detail": detail}


def convert_to_jsonl(
    path: str | Path,
    output: str | Path,
    service_name: str = "mas-runtime",
    app_name: str = "",
) -> dict:
    """Convert *path* to OTLP JSON spans and write to *output* (JSONL, no push).

    Each line of *output* is a JSON-serialised OTLP ``ResourceSpans`` object.
    The file is safe to feed to ``push_file`` later or to any OTel-aware tool.

    Parameters
    ----------
    app_name:
        When non-empty, sets ``application_id`` on every span so Claris groups
        traces under this application name.  Defaults to *service_name*.

    Returns a summary dict::

        {"spans": int, "status": "ok" | "error", "detail": str}
    """
    first = load_events(path)[:1]
    if not first:
        return {"spans": 0, "status": "ok", "detail": "empty file"}
    first = first[0]

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    effective_app_name = app_name or service_name

    if "context" in first and isinstance(first.get("context"), dict) and "trace_id" in first["context"]:
        # Already OTel SDK spans — convert and write as OTLP payload.
        # service.name is already set on the resource by the plugin/converter;
        # only fill a fallback if the spans don't carry one.
        events = load_events(path)
        spans = _sdk_spans_to_otlp(events)
        resource_attrs = _resource_from_sdk(first)
        resource_attrs.setdefault("service.name", service_name)
        for s in spans:
            s.attributes["application_id"] = effective_app_name
        payload = _build_otlp_payload(spans, resource_attrs)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
        return {"spans": len(spans), "status": "ok", "detail": str(out_path)}
    else:
        # MAS native events — use the authoritative MasOtelConverter.
        # Output is OTel SDK spans JSONL (one span per line), accepted by push_file.
        from mas.library.standard.plugins.observability.otel.converter import (
            MasOtelConverter,
        )
        MasOtelConverter.replay_file(
            path, out_path,
            service_name=service_name,
            app_name=effective_app_name,
        )
        span_count = sum(1 for _ in open(out_path, encoding="utf-8") if _)
        return {"spans": span_count, "status": "ok", "detail": str(out_path)}


# ---------------------------------------------------------------------------
# OTel SDK span.to_json() → OTLP spans
# ---------------------------------------------------------------------------

# (MAS native events → OTel SDK spans is handled by MasOtelConverter.replay_file
# in mas.library.standard.plugins.observability.otel — the single authoritative
# converter that supports all event kinds defined in the MAS runtime.)

_SDK_KIND_MAP = {
    "SpanKind.INTERNAL": 1,
    "SpanKind.SERVER": 2,
    "SpanKind.CLIENT": 3,
    "SpanKind.PRODUCER": 4,
    "SpanKind.CONSUMER": 5,
}

_SDK_STATUS_MAP = {
    "OK": 1,
    "ERROR": 2,
    "UNSET": 0,
}


def _sdk_spans_to_otlp(sdk_spans: list[dict]) -> list[OtlpSpan]:
    """Convert Python OTel SDK span.to_json() records to OtlpSpan objects."""
    spans = []
    for raw in sdk_spans:
        ctx = raw.get("context", {})
        trace_id = _normalise_hex(ctx.get("trace_id", ""), 32)
        span_id = _normalise_hex(ctx.get("span_id", ""), 16)
        if not trace_id or not span_id:
            continue
        parent_id_raw = raw.get("parent_id")
        parent_span_id = _normalise_hex(parent_id_raw, 16) if parent_id_raw else None

        name = raw.get("name", "span")
        kind = _SDK_KIND_MAP.get(raw.get("kind", ""), 1)
        start_ns = _iso_to_ns(raw.get("start_time", ""))
        end_ns = _iso_to_ns(raw.get("end_time", ""))
        status_code = _SDK_STATUS_MAP.get(
            (raw.get("status") or {}).get("status_code", "UNSET"), 0
        )

        raw_attrs = raw.get("attributes") or {}
        attrs: dict = dict(raw_attrs)

        spans.append(OtlpSpan(
            trace_id=trace_id,
            span_id=span_id,
            name=name,
            start_ns=start_ns,
            end_ns=max(end_ns, start_ns + 1),
            kind=kind,
            parent_span_id=parent_span_id,
            attributes=attrs,
            status_code=status_code,
        ))
    return spans


def _resource_from_sdk(first_span: dict) -> dict:
    """Extract resource attributes from the first SDK span."""
    res = first_span.get("resource") or {}
    raw_attrs = res.get("attributes") or {}
    return dict(raw_attrs)


# ---------------------------------------------------------------------------
# OTLP HTTP push
# ---------------------------------------------------------------------------

def _build_otlp_payload(spans: list[OtlpSpan], resource_attrs: dict) -> dict:
    return {
        "resourceSpans": [{
            "resource": {"attributes": _attrs_to_otlp(resource_attrs)},
            "scopeSpans": [{
                "scope": {"name": "mas-lab-push", "version": "1.0"},
                "spans": [s.to_otlp_dict() for s in spans],
            }],
        }]
    }


def _http_post_json(url: str, payload: dict) -> Optional[str]:
    """POST JSON payload to *url*. Returns None on success, error string on failure."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                return f"HTTP {resp.status}"
        return None
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")[:200]
        return f"HTTP {exc.code}: {body_text}"
    except Exception as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iso_to_ns(iso: str) -> int:
    """ISO-8601 string (``2024-01-01T00:00:00.000000Z``) → Unix nanoseconds."""
    iso = iso.rstrip("Z").replace(" ", "T")
    # Remove sub-microsecond precision beyond 6 decimals
    iso = re.sub(r"(\.\d{6})\d+", r"\1", iso)
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _normalise_hex(value: str, length: int) -> str:
    """Strip ``0x`` prefix, lowercase, zero-pad to *length* chars."""
    if not value:
        return ""
    h = value.lower().lstrip("0x") if value.startswith("0x") else value.lower()
    return h.zfill(length)[:length]


def _attrs_to_otlp(attrs: dict) -> list[dict]:
    """Convert a plain dict to the OTLP ``[{key, value: {xValue}}]`` format."""
    result = []
    for k, v in attrs.items():
        if isinstance(v, bool):
            val = {"boolValue": v}
        elif isinstance(v, int):
            val = {"intValue": str(v)}    # OTLP JSON uses string for int64
        elif isinstance(v, float):
            val = {"doubleValue": v}
        else:
            val = {"stringValue": str(v)}
        result.append({"key": str(k), "value": val})
    return result
