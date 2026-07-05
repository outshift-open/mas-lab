#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Boundary event kind dispatch — one handler per ``ObsEventKind``."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from mas.library.standard.lib.observability.native.tool_name import resolve_tool_name
from mas.runtime.schema.observability import ObsEventKind

if TYPE_CHECKING:
    from mas.library.standard.lib.observability.native.transform import TransformContext


def dispatch_boundary(record: dict, *, ctx: TransformContext) -> list[dict]:
    """Route one boundary record to its kind handler."""
    from mas.library.standard.lib.observability.native.transform import _event_kind

    kind = _event_kind(record)
    handler = _BOUNDARY_KIND_HANDLERS.get(kind)
    if handler is None:
        return []
    cid = int(record.get("correlation_id") or 0)
    base = {"agent_id": ctx.agent_id, "run_id": ctx.run_id, "correlation_id": cid}
    payload = record.get("payload") or {}
    ts = time.time()
    return handler(record, ctx=ctx, cid=cid, base=base, payload=payload, ts=ts)


def _boundary_engine_io(
    record: dict,
    *,
    ctx: TransformContext,
    cid: int,
    base: dict,
    payload: dict,
    ts: float,
) -> list[dict]:
    from mas.library.standard.lib.observability.native.transform import _resolve_call_id, _with_parent

    out: list[dict] = []
    op = payload.get("op", "")
    key = (cid, op)
    if op == "MEMORY_OP" and key not in ctx._seen_engine_ops:
        ctx._seen_engine_ops.add(key)
        rec = {
            "kind": "memory_call_start",
            **base,
            "call_id": _resolve_call_id(record, ctx, cid, "MEMORY_OP"),
            "timestamp": ts,
        }
        out.append(_with_parent(rec, record, ctx))
    if op == "LLM_CALL" and key not in ctx._seen_engine_ops:
        ctx._seen_engine_ops.add(key)
        messages = payload.get("messages") or []
        rec = {
            "kind": "llm_call_start",
            **base,
            "call_id": _resolve_call_id(record, ctx, cid, "LLM_CALL"),
            "timestamp": ts,
            **({"messages": messages} if messages else {}),
        }
        out.append(_with_parent(rec, record, ctx))
    if op == "TOOL_CALL" and key not in ctx._seen_engine_ops:
        ctx._seen_engine_ops.add(key)
        tool_rec: dict = {
            "kind": "tool_call_start",
            **base,
            "call_id": _resolve_call_id(record, ctx, cid, "TOOL_CALL"),
            "timestamp": ts,
            "tool_name": resolve_tool_name(payload),
        }
        args = payload.get("tool_arguments")
        if isinstance(args, dict) and args:
            tool_rec["arguments"] = args
        out.append(_with_parent(tool_rec, record, ctx))
    return out


def _boundary_engine_io_return(
    record: dict,
    *,
    ctx: TransformContext,
    cid: int,
    base: dict,
    payload: dict,
    ts: float,
) -> list[dict]:
    from mas.library.standard.lib.observability.native.transform import _resolve_call_id, _with_parent

    out: list[dict] = []
    op = payload.get("op", "LLM_CALL")
    key = (cid, op)
    if op == "LLM_CALL" and key not in ctx._seen_engine_returns:
        ctx._seen_engine_returns.add(key)
        rec = {
            "kind": "llm_call_end",
            **base,
            "call_id": _resolve_call_id(record, ctx, cid, "LLM_CALL"),
            "timestamp": ts,
            "output": payload.get("text", ""),
            "next_step": payload.get("next_step", "STOP"),
        }
        out.append(_with_parent(rec, record, ctx))
    if op == "TOOL_CALL" and key not in ctx._seen_engine_returns:
        ctx._seen_engine_returns.add(key)
        rec = {
            "kind": "tool_call_end",
            **base,
            "call_id": _resolve_call_id(record, ctx, cid, "TOOL_CALL"),
            "timestamp": ts,
            "output": payload.get("text", ""),
            "tool_name": resolve_tool_name(payload),
        }
        out.append(_with_parent(rec, record, ctx))
    if op == "MEMORY_OP" and key not in ctx._seen_engine_returns:
        ctx._seen_engine_returns.add(key)
        rec = {
            "kind": "memory_call_end",
            **base,
            "call_id": _resolve_call_id(record, ctx, cid, "MEMORY_OP"),
            "timestamp": ts,
            "output": payload.get("text", ""),
        }
        out.append(_with_parent(rec, record, ctx))
    return out


def _boundary_envelope_activity(
    record: dict,
    *,
    ctx: TransformContext,
    cid: int,
    base: dict,
    payload: dict,
    ts: float,
) -> list[dict]:
    from mas.library.standard.lib.observability.native.transform import _resolve_call_id, _with_parent

    activity = payload.get("activity", "")
    boundary = payload.get("boundary", "")
    op_name = payload.get("op", "")
    if boundary not in ("start", "end"):
        return []
    native_kind = f"{activity}_{boundary}"
    if activity == "contract_call":
        if op_name == "TOOL_CALL":
            native_kind = f"tool_call_{boundary}"
        elif op_name == "MEMORY_OP":
            native_kind = f"memory_call_{boundary}"
        else:
            native_kind = f"llm_call_{boundary}"
    elif activity == "parallel_group":
        native_kind = f"parallel_group_{boundary}"
    elif activity in ("gov_authorize", "gov_validate"):
        native_kind = f"governance_{activity.replace('gov_', '')}_{boundary}"
    elif activity.startswith("obs_wrap"):
        native_kind = f"{activity}_{boundary}"
    call_id = _resolve_call_id(record, ctx, cid, op_name or activity)
    tool_name = resolve_tool_name(payload) if op_name == "TOOL_CALL" or "tool_call" in native_kind else ""
    rec = {
        "kind": native_kind,
        **base,
        "timestamp": ts,
        "call_id": call_id,
        "activity": activity,
        "op": op_name,
        **({"tool_name": tool_name} if tool_name or op_name == "TOOL_CALL" or "tool_call" in native_kind else {}),
        **(
            {"group_id": payload.get("group_id", ""), "tools": payload.get("tools", [])}
            if activity == "parallel_group"
            else {}
        ),
    }
    return [_with_parent(rec, record, ctx)]


def _boundary_context_assembled(
    record: dict,
    *,
    ctx: TransformContext,
    cid: int,
    base: dict,
    payload: dict,
    ts: float,
) -> list[dict]:
    from mas.library.standard.lib.observability.native.transform import (
        _SYNTHETIC_SPAN_DURATION_S,
        _with_parent,
    )

    llm_call_id = f"llm-{cid}" if cid else ""
    segments = payload.get("segments") or []
    out: list[dict] = [
        {
            "kind": "context_assembled",
            **base,
            "timestamp": ts,
            "call_id": llm_call_id,
            "llm_call_id": llm_call_id,
            "segments": len(segments),
            "total_tokens": payload.get("total_tokens", 0),
            "message_count": payload.get("message_count", 0),
        }
    ]
    agent_id = payload.get("agent_id") or ctx.agent_id
    for seg in segments:
        mechanism = str(seg.get("mechanism") or "")
        source = str(seg.get("source") or "")
        is_rag = mechanism == "rag" or "rag" in source.lower()
        out.append(
            {
                "kind": "context_part_contributed",
                "agent_id": agent_id,
                "timestamp": ts,
                "llm_call_id": llm_call_id,
                "part_id": seg.get("part_id", ""),
                "source": seg.get("source", ""),
                "section_id": seg.get("section_id", ""),
                "mechanism": seg.get("mechanism") or ("rag" if is_rag else "inject"),
                "token_estimate": seg.get("tokens", 0),
                "retained": seg.get("retained", True),
                "content_preview": seg.get("content_preview", ""),
                "role": seg.get("role", ""),
            }
        )
        if is_rag:
            rag_call_id = f"rag-{cid}-{seg.get('part_id', '')[:8]}"
            out.extend(
                [
                    _with_parent(
                        {
                            "kind": "rag_query_start",
                            **base,
                            "timestamp": ts,
                            "call_id": rag_call_id,
                            "query": seg.get("content_preview", ""),
                        },
                        record,
                        ctx,
                    ),
                    _with_parent(
                        {
                            "kind": "rag_query_end",
                            **base,
                            "timestamp": ts + _SYNTHETIC_SPAN_DURATION_S,
                            "call_id": rag_call_id,
                            "results_count": 1,
                            "synthetic": True,
                        },
                        record,
                        ctx,
                    ),
                ]
            )
    return out


def _boundary_context_mutation(
    record: dict,
    *,
    ctx: TransformContext,
    cid: int,
    base: dict,
    payload: dict,
    ts: float,
) -> list[dict]:
    from mas.library.standard.lib.observability.native.transform import _SYNTHETIC_SPAN_DURATION_S

    action = payload.get("action", "mutation")
    state_call_id = f"state-{cid}-{action}-{payload.get('turn_index', 0)}"
    return [
        {
            "kind": "state_update_start",
            **base,
            "timestamp": ts,
            "call_id": state_call_id,
            "update_type": action,
            "role": payload.get("role", ""),
            "turn_index": payload.get("turn_index", 0),
            "committed_count": payload.get("committed_count", 0),
            "wm_count": payload.get("wm_count", 0),
        },
        {
            "kind": "state_update_end",
            **base,
            "timestamp": ts + _SYNTHETIC_SPAN_DURATION_S,
            "call_id": state_call_id,
            "update_type": action,
            "content_preview": payload.get("content_preview", ""),
            "synthetic": True,
        },
    ]


def _boundary_client_response(
    record: dict,
    *,
    ctx: TransformContext,
    cid: int,
    base: dict,
    payload: dict,
    ts: float,
) -> list[dict]:
    return [
        {
            "kind": "client_response",
            **base,
            "timestamp": ts,
            "finish_reason": payload.get("finish_reason", "stop"),
        }
    ]


def _boundary_hitl_request(
    record: dict,
    *,
    ctx: TransformContext,
    cid: int,
    base: dict,
    payload: dict,
    ts: float,
) -> list[dict]:
    return [
        {
            "kind": "hitl_gate",
            **base,
            "timestamp": ts,
            "question": payload.get("question", ""),
        }
    ]


_BoundaryHandler = Callable[..., list[dict]]

_BOUNDARY_KIND_HANDLERS: dict[str, _BoundaryHandler] = {
    ObsEventKind.ENGINE_IO.value: _boundary_engine_io,
    ObsEventKind.ENGINE_IO_RETURN.value: _boundary_engine_io_return,
    ObsEventKind.ENVELOPE_ACTIVITY.value: _boundary_envelope_activity,
    ObsEventKind.CONTEXT_ASSEMBLED.value: _boundary_context_assembled,
    ObsEventKind.CONTEXT_MUTATION.value: _boundary_context_mutation,
    ObsEventKind.CLIENT_RESPONSE.value: _boundary_client_response,
    ObsEventKind.HITL_REQUEST.value: _boundary_hitl_request,
}
