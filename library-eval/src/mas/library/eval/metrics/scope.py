#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Evidence a metric implementation asked for (I/O pair vs event history).

This is part of the metric, not of the pipeline step. Stock MCE session ids
are MAS input/output. Inline ``prompt_metrics`` and ``EvalMetric`` plugins
declare ``unit`` and ``evidence`` on the metric itself. ``eval_mce`` only
runs whatever ids it is given.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

UNITS = ("mas", "agent", "call")
EVIDENCE_KINDS = ("io", "trajectory")
Unit = Literal["mas", "agent", "call"]
Evidence = Literal["io", "trajectory"]

MAX_TRACE_CHARS = 350_000


def parse_unit(raw: Any, *, field: str = "unit") -> Unit:
    token = str(raw or "").strip().lower()
    if token == "session":
        token = "mas"
    if token == "span":
        token = "call"
    if token not in UNITS:
        raise ValueError(
            f"{field} must be one of {list(UNITS)} "
            f"(mas = the run, agent = one agent, call = one LLM/tool call); got {raw!r}"
        )
    return token  # type: ignore[return-value]


def parse_evidence(raw: Any, *, field: str = "evidence") -> Evidence:
    token = str(raw or "").strip().lower()
    if token in {"i/o", "input_output", "input-output"}:
        token = "io"
    if token in {"trace", "events", "native_trace"}:
        token = "trajectory"
    if token not in EVIDENCE_KINDS:
        raise ValueError(
            f"{field} must be one of {list(EVIDENCE_KINDS)} "
            f"(io = that unit's input and output only, trajectory = event history); "
            f"got {raw!r}"
        )
    return token  # type: ignore[return-value]


def scope_details(
    unit: str,
    evidence: str,
    **extra: Any,
) -> dict[str, Any]:
    """Fields to store on MetricScore.details so the slice is visible in metrics.json."""
    out: dict[str, Any] = {"unit": unit, "evidence": evidence}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def render_judge_input(
    events_path: Path,
    *,
    unit: str,
    evidence: str,
    agent_id: str | None = None,
    call_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the text appended after the metric prompt.

    Uses :class:`MASTraceProvider.fetch` for I/O extraction. Returns
    ``(text, meta)`` where *meta* is merged into score details.
    """
    from mas.library.eval.mce.trace_provider import MASTraceProvider

    unit_n = parse_unit(unit)
    evidence_n = parse_evidence(evidence)
    if unit_n == "call":
        raise ValueError(
            "unit=call is not scored by eval_mce: metrics.json holds one "
            "session score per id. Use unit=mas or unit=agent."
        )
    if unit_n == "agent" and not str(agent_id or "").strip():
        raise ValueError("unit=agent requires agent (agent_id of the I/O pair)")

    aid = str(agent_id).strip() if agent_id else None
    provider = MASTraceProvider(response_agent_id=aid if unit_n == "agent" else None)
    ctx = provider.fetch(str(events_path), requirements=None)
    events = list(ctx.get("events") or [])
    truncated = False
    if evidence_n == "io":
        if unit_n == "mas":
            inp = ctx.get("input_query") or ""
            out = ctx.get("final_response") or ""
        else:
            inp = _agent_start_input(events, aid or "")
            out = ctx.get("final_response") or ""
        text = f"## UNIT {unit_n} (I/O)\n## INPUT\n{inp}\n\n## OUTPUT\n{out}\n"
    else:
        body, truncated = _trajectory_text(
            events_path,
            events,
            unit=unit_n,
            agent_id=aid,
        )
        text = f"## UNIT {unit_n} (trajectory)\n## TRACE\n{body}\n"
        if truncated:
            text += f"\n[trace truncated to {MAX_TRACE_CHARS} characters]\n"

    meta = scope_details(
        unit_n,
        evidence_n,
        agent_id=aid,
        call_id=str(call_id).strip() if call_id else None,
        truncated=truncated,
    )
    return text, meta


def _agent_start_input(events: list[dict[str, Any]], agent_id: str) -> str:
    for event in events:
        if event.get("kind") == "execution_start" and str(event.get("agent_id") or "") == agent_id:
            value = event.get("input")
            if value:
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return ""


def _trajectory_text(
    path: Path,
    events: list[dict[str, Any]],
    *,
    unit: str,
    agent_id: str | None,
) -> tuple[str, bool]:
    if unit == "mas":
        text = path.read_text(encoding="utf-8")
        if len(text) <= MAX_TRACE_CHARS:
            return text, False
        return text[:MAX_TRACE_CHARS], True
    aid = str(agent_id or "").strip()
    lines = [json.dumps(event, ensure_ascii=False) for event in events if str(event.get("agent_id") or "") == aid]
    text = "\n".join(lines) + ("\n" if lines else "")
    if len(text) <= MAX_TRACE_CHARS:
        return text, False
    return text[:MAX_TRACE_CHARS], True
