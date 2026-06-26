#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Event transforms — pure boundary → native → otel (no I/O)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from mas.runtime.schema.observability import ObsEventKind, ObservabilityEvent


@runtime_checkable
class EventTransform(Protocol):
    """Map one or more input records to output records (chainable, side-effect free)."""

    transform_id: str

    def transform(self, record: dict, *, ctx: TransformContext) -> list[dict]: ...


@dataclass
class TransformContext:
    agent_id: str = "agent"
    run_id: str = ""
    turn_id: str = ""
    _seen_engine_ops: set[tuple[int, str]] = field(default_factory=set)
    _seen_engine_returns: set[tuple[int, str]] = field(default_factory=set)


class BoundaryPassthroughTransform:
    """Emit v2 boundary audit events as JSON (schema: observability)."""

    transform_id = "boundary"

    def transform(self, record: dict, *, ctx: TransformContext) -> list[dict]:
        if record.get("_source") != "boundary":
            return []
        out = dict(record)
        out.pop("_source", None)
        out.setdefault("agent_id", ctx.agent_id)
        out.setdefault("run_id", ctx.run_id)
        return [out]


class NativeObservabilityTransform:
    """Map v2 boundary + session records to mas-lab native events.jsonl shape."""

    transform_id = "native"

    def transform(self, record: dict, *, ctx: TransformContext) -> list[dict]:
        source = record.get("_source")
        if source == "session":
            return self._session(record, ctx)
        if source == "boundary":
            return self._boundary(record, ctx=ctx)
        return []

    def _session(self, record: dict, ctx: TransformContext) -> list[dict]:
        kind = record.get("session_kind")
        base = {"agent_id": ctx.agent_id, "run_id": ctx.run_id, "turn_id": ctx.turn_id}
        if kind == "user_input":
            return [
                {
                    "kind": "execution_start",
                    **base,
                    "call_id": f"{ctx.turn_id}-exec",
                    "input": record.get("text", ""),
                }
            ]
        if kind == "agent_response":
            return [
                {
                    "kind": "user_response",
                    **base,
                    "call_id": f"{ctx.turn_id}-resp",
                    "content": record.get("text", ""),
                    "finish_reason": record.get("finish_reason", "stop"),
                },
                {
                    "kind": "execution_end",
                    **base,
                    "call_id": f"{ctx.turn_id}-exec",
                    "status": "ok",
                },
            ]
        return []

    def _boundary(self, record: dict, *, ctx: TransformContext) -> list[dict]:
        kind = record.get("kind", "")
        cid = int(record.get("correlation_id") or 0)
        base = {"agent_id": ctx.agent_id, "run_id": ctx.run_id, "correlation_id": cid}
        payload = record.get("payload") or {}
        ts = time.time()
        out: list[dict] = []

        if kind == ObsEventKind.ENGINE_IO.value or kind == "engine.io":
            op = payload.get("op", "")
            key = (cid, op)
            if op == "LLM_CALL" and key not in ctx._seen_engine_ops:
                ctx._seen_engine_ops.add(key)
                messages = payload.get("messages") or []
                out.append(
                    {
                        "kind": "llm_call_start",
                        **base,
                        "call_id": f"llm-{cid}",
                        "timestamp": ts,
                        **({"messages": messages} if messages else {}),
                    }
                )
            if op == "TOOL_CALL" and key not in ctx._seen_engine_ops:
                ctx._seen_engine_ops.add(key)
                out.append(
                    {
                        "kind": "tool_call_start",
                        **base,
                        "call_id": f"tool-{cid}",
                        "timestamp": ts,
                        "tool_name": payload.get("tool_name", ""),
                    }
                )

        if kind == ObsEventKind.ENGINE_IO_RETURN.value or kind == "engine.io.return":
            op = payload.get("op", "LLM_CALL")
            key = (cid, op)
            if op == "LLM_CALL" and key not in ctx._seen_engine_returns:
                ctx._seen_engine_returns.add(key)
                out.append(
                    {
                        "kind": "llm_call_end",
                        **base,
                        "call_id": f"llm-{cid}",
                        "timestamp": ts,
                        "output": payload.get("text", ""),
                        "next_step": payload.get("next_step", "STOP"),
                    }
                )
            if op == "TOOL_CALL" and key not in ctx._seen_engine_returns:
                ctx._seen_engine_returns.add(key)
                out.append(
                    {
                        "kind": "tool_call_end",
                        **base,
                        "call_id": f"tool-{cid}",
                        "timestamp": ts,
                        "output": payload.get("text", ""),
                        "tool_name": payload.get("tool_name", ""),
                    }
                )

        if kind == ObsEventKind.ENVELOPE_ACTIVITY.value or kind == "envelope.activity":
            activity = payload.get("activity", "")
            boundary = payload.get("boundary", "")
            op_name = payload.get("op", "")
            if boundary not in ("start", "end"):
                return out
            native_kind = f"{activity}_{boundary}"
            if activity == "contract_call":
                native_kind = (
                    f"{'tool' if op_name == 'TOOL_CALL' else 'llm'}_call_{boundary}"
                )
            elif activity in ("gov_authorize", "gov_validate"):
                native_kind = f"governance_{activity.replace('gov_', '')}_{boundary}"
            elif activity.startswith("obs_wrap"):
                native_kind = f"{activity}_{boundary}"
            call_id = f"{op_name.lower().replace('_call', '')}-{cid}" if cid else activity
            if op_name == "TOOL_CALL":
                call_id = f"tool-{cid}"
            elif op_name == "LLM_CALL":
                call_id = f"llm-{cid}"
            out.append(
                {
                    "kind": native_kind,
                    **base,
                    "timestamp": ts,
                    "call_id": call_id,
                    "activity": activity,
                    "op": op_name,
                    **(
                        {"tool_name": payload.get("tool_name", "")}
                        if payload.get("tool_name")
                        else {}
                    ),
                }
            )

        if kind == ObsEventKind.CONTEXT_ASSEMBLED.value or kind == "context.assembled":
            llm_call_id = f"llm-{cid}" if cid else ""
            segments = payload.get("segments") or []
            out.append(
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
            )
            agent_id = payload.get("agent_id") or ctx.agent_id
            for seg in segments:
                out.append(
                    {
                        "kind": "context_part_contributed",
                        "agent_id": agent_id,
                        "timestamp": ts,
                        "llm_call_id": llm_call_id,
                        "part_id": seg.get("part_id", ""),
                        "source": seg.get("source", ""),
                        "section_id": seg.get("section_id", ""),
                        "mechanism": "inject",
                        "token_estimate": seg.get("tokens", 0),
                        "retained": seg.get("retained", True),
                        "content_preview": seg.get("content_preview", ""),
                        "role": seg.get("role", ""),
                    }
                )

        if kind == ObsEventKind.CONTEXT_MUTATION.value or kind == "context.mutation":
            action = payload.get("action", "mutation")
            state_call_id = f"state-{cid}-{action}-{payload.get('turn_index', 0)}"
            out.extend(
                [
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
                        "timestamp": ts + 0.001,
                        "call_id": state_call_id,
                        "update_type": action,
                        "content_preview": payload.get("content_preview", ""),
                    },
                ]
            )

        if kind == ObsEventKind.CLIENT_RESPONSE.value or kind == "client.response":
            out.append(
                {
                    "kind": "context_assembled",
                    **base,
                    "timestamp": ts,
                    "finish_reason": payload.get("finish_reason", "stop"),
                }
            )

        if kind == ObsEventKind.HITL_REQUEST.value or kind == "hitl.request":
            out.append(
                {
                    "kind": "hitl_gate",
                    **base,
                    "timestamp": ts,
                    "question": payload.get("question", ""),
                }
            )
        return out


class OtelSpanTransform:
    """Transform native-shaped records to simplified OTel span JSONL (offline / dual-file)."""

    transform_id = "otel"

    _START = {
        "llm_call_start",
        "tool_call_start",
        "execution_start",
        "mas_call_start",
        "state_update_start",
    }
    _END = {
        "llm_call_end",
        "tool_call_end",
        "execution_end",
        "mas_call_end",
        "user_response",
        "state_update_end",
    }

    def transform(self, record: dict, *, ctx: TransformContext) -> list[dict]:
        kind = record.get("kind", "")
        if kind not in self._START | self._END | {"context_assembled", "hitl_gate", "context_part_contributed"}:
            return []
        span_name = kind.replace("_", ".")
        return [
            {
                "schema": "otel_span_v1",
                "name": span_name,
                "trace_id": ctx.run_id or "local",
                "span_id": record.get("call_id") or f"{kind}-{record.get('correlation_id', 0)}",
                "agent_id": ctx.agent_id,
                "attributes": {k: v for k, v in record.items() if k not in ("kind", "timestamp")},
            }
        ]
