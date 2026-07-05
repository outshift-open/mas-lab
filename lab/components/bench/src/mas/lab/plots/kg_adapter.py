#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Adapters for loading kg.json as plotter input.

Converts kg.json graph nodes into the same internal formats that the
plotters already expect, so they can consume kg.json **directly** without
going through events.jsonl or normalized_trace.jsonl.

Two adapters:

* :func:`kg_to_call_records` — converts kg nodes → ``_build_call_records``
  record format (for :mod:`multilevel_trajectory` and :mod:`communication_flow`).
* :func:`kg_to_delegations` — converts kg routing edges → delegation dicts
  (for :mod:`trajectory`).
* :func:`load_kg` — auto-detects kg.json and returns events-compatible dicts
  (thin wrapper for ``load_trace`` backward compat).

Faceted query layer
-------------------
* :class:`FacetQuery` — lightweight filter spec (Python port of the JS
  FacetBrowser ``TransformState``).  JSON-serialisable for WebSocket transport.
* :class:`KGSource` — high-level data source that applies a :class:`FacetQuery`
  to a KG and returns the ``(records, events)`` pair expected by the plotters.
* :class:`KGView` — low-level faceted access layer (``query(call_type, **kw)``
  + O(1) ``get(call_id)``).

Future path
-----------
The same ``FacetQuery`` schema will be used for WebSocket-based streaming in
the UI:  JS sends a ``TransformState``-shaped JSON object, the backend deserialises
it into a ``FacetQuery`` via :meth:`FacetQuery.from_dict`, runs ``KGSource.load()``,
and streams the resulting chart JSON back to the browser.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterator, TypedDict, Union

logger = logging.getLogger(__name__)


class KGStreamChunk(TypedDict):
    """Single chunk yielded by :meth:`KGSource.stream`.

    ``done=True`` marks the final chunk — consumers should stop iterating.
    The same shape is emitted over WebSocket to the browser (JSON-serialisable).
    """
    records: list[dict[str, Any]]
    events:  list[dict[str, Any]]
    done:    bool

# Node-type → call_type mapping (matches multilevel_trajectory._KIND_BASE_TO_TYPE)
_NODE_TYPE_TO_CALL_TYPE: dict[str, str] = {
    "AgentCall":      "AgentCall",
    "LLMCall":        "LLMCall",
    "ToolCall":       "ToolCall",
    "SkillCall":      "SkillCall",
    "ProcessingCall": "ProcessingCall",
    "ThinkingCall":   "ThinkingCall",
    "MITMCall":       "MITMCall",
    "MASCall":        "MASCall",
    "TaskCall":       "TaskCall",
}

_CALL_TYPE_TO_LEVEL: dict[str, str] = {
    "AgentCall":      "agent",
    "LLMCall":        "call",
    "ToolCall":       "call",
    "SkillCall":      "call",
    "ProcessingCall": "call",
    "ThinkingCall":   "call",
    "MITMCall":       "call",
    "MASCall":        "mas",
    "TaskCall":       "task",
}


def load_kg(source: Union[str, Path]) -> dict[str, Any]:
    """Load a kg.json file and return the parsed dict.

    Returns ``{"nodes": [...], "edges": [...], "run_id": ..., "meta": ...}``.
    """
    path = Path(source).expanduser()
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def kg_to_call_records(kg: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert kg.json nodes into the record dicts expected by plotters.

    Returns a list sorted by ``start_ts``, with keys matching the output of
    ``multilevel_trajectory._build_call_records()``:

    ``call_id, parent_call_id, call_type, level, agent_id,
    start_ts, end_ts, input, output, label, tool_name, model,
    thinking, processing_name, _has_ids``
    """
    nodes = kg.get("nodes", [])
    records: list[dict[str, Any]] = []

    for node in nodes:
        ntype = node.get("node_type", "")
        call_type = _NODE_TYPE_TO_CALL_TYPE.get(ntype)
        if call_type is None:
            continue

        record: dict[str, Any] = {
            "call_id":        node.get("callId") or node.get("id", ""),
            "parent_call_id": node.get("parentCallId"),
            "_has_ids":       True,  # KG always has call_ids
            "call_type":      call_type,
            "level":          _CALL_TYPE_TO_LEVEL.get(call_type, "call"),
            "agent_id":       node.get("agentId") or node.get("agentName", ""),
            "start_ts":       float(node.get("startTime") or 0),
            "end_ts":         float(node.get("endTime") or 0),
            "input":          "",
            "output":         "",
            "label":          "",
            "tool_name":      "",
            "model":          "",
            "thinking":       "",
            "processing_name": "",
        }

        # -- Populate type-specific fields --
        if call_type == "AgentCall":
            record["input"] = node.get("inputContent", "")
            record["output"] = node.get("outputContent", "")
            record["label"] = node.get("agentName") or node.get("agentId", "")
            status = node.get("status", "")
            if status and status not in ("success", "ok", ""):
                record["_exec_status"] = status

        elif call_type == "LLMCall":
            record["input"] = node.get("prompt", "")
            record["output"] = node.get("completion", "")
            record["model"] = node.get("modelName") or node.get("llmName", "")
            record["thinking"] = node.get("thinking", "")
            record["label"] = record["model"] or "LLM"

        elif call_type == "ToolCall":
            record["tool_name"] = node.get("toolName", "")
            record["input"] = node.get("toolArguments", "")
            record["output"] = node.get("toolOutput", "")
            record["label"] = record["tool_name"] or "tool"
            if not record["input"] or record["input"] in ("", "{}", "null", "None"):
                record["input"] = f"→ {record['tool_name'] or 'tool'}()"

        elif call_type == "SkillCall":
            record["processing_name"] = node.get("skillName", "")
            record["input"] = node.get("skillInput", "")
            record["output"] = node.get("skillOutput", "")
            record["label"] = record["processing_name"] or "skill"

        elif call_type == "ProcessingCall":
            record["processing_name"] = node.get("processingName", "")
            record["input"] = node.get("inputContent", "")
            record["output"] = node.get("outputContent", "")
            record["label"] = record["processing_name"] or "processing"

        elif call_type == "ThinkingCall":
            record["input"] = node.get("inputContent", "")
            record["output"] = node.get("outputContent", "")
            record["label"] = "thinking"

        elif call_type == "MITMCall":
            record["input"] = node.get("inputContent", "")
            record["output"] = node.get("outputContent", "")
            record["label"] = "MITM"
            record["processing_name"] = "mitm_rewrite"

        records.append(record)

    records.sort(key=lambda r: r["start_ts"])
    return records


def _normalize_timestamps(
    records: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> float:
    """Shift all timestamps so the trace starts at t=0. Returns the offset."""
    candidates: list[float] = []
    for rec in records:
        if rec.get("start_ts"):
            candidates.append(float(rec["start_ts"]))
        if rec.get("end_ts"):
            candidates.append(float(rec["end_ts"]))
    for ev in events:
        ts = ev.get("timestamp")
        if ts is not None:
            candidates.append(float(ts))
    if not candidates:
        return 0.0
    t_max = max(candidates)
    # Absolute Unix epoch timestamps (not relative offsets) — normalize to t=0.
    if t_max < 1e6:
        return 0.0
    positive = [t for t in candidates if t > 1.0]
    offset = min(positive) if positive else min(candidates)
    if offset <= 0.0:
        return 0.0
    for rec in records:
        rec["start_ts"] = float(rec.get("start_ts") or 0) - offset
        rec["end_ts"] = float(rec.get("end_ts") or 0) - offset
        rec["start_ts"] = max(0.0, rec["start_ts"])
        rec["end_ts"] = max(rec["start_ts"], rec["end_ts"])
    for ev in events:
        ev["timestamp"] = max(0.0, float(ev.get("timestamp") or 0) - offset)
    return offset


def _synthesize_agent_calls(
    kg: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create AgentCall records for agents that only appear as LLM/Tool calls."""
    nodes = kg.get("nodes", [])
    edges = kg.get("edges", [])

    existing_agents = {
        r.get("agent_id")
        for r in records
        if r.get("call_type") == "AgentCall" and r.get("agent_id")
    }

    # Map delegated agent → delegating tool call id (callsAgent edges).
    delegate_parent: dict[str, str] = {}
    nodes_by_id = {n.get("id", ""): n for n in nodes}
    for edge in edges:
        if (edge.get("edge_type") or edge.get("type")) != "callsAgent":
            continue
        tgt = edge.get("target") or edge.get("to_id") or ""
        src = edge.get("source") or edge.get("from_id") or ""
        agent_id = tgt
        if tgt in nodes_by_id:
            agent_id = (
                nodes_by_id[tgt].get("agentId")
                or nodes_by_id[tgt].get("agentName")
                or tgt
            )
        if agent_id and src:
            delegate_parent[str(agent_id)] = str(src)

    # Root agent AgentCall (entry orchestrator).
    root_agent_call = next(
        (r for r in records if r.get("call_type") == "AgentCall" and not r.get("parent_call_id")),
        None,
    )
    if root_agent_call is None:
        root_agent_call = next(
            (r for r in records if r.get("call_type") == "AgentCall"),
            None,
        )
    root_parent = root_agent_call.get("call_id") if root_agent_call else None

    work_agents: dict[str, list[dict]] = {}
    for rec in records:
        if rec.get("call_type") not in {"LLMCall", "ToolCall", "ProcessingCall"}:
            continue
        aid = rec.get("agent_id") or ""
        if not aid or aid in {"mas", "agent"}:
            continue
        work_agents.setdefault(aid, []).append(rec)

    synth: list[dict[str, Any]] = []
    for agent_id, calls in sorted(work_agents.items()):
        if agent_id in existing_agents:
            continue
        start_ts = min(float(c.get("start_ts") or 0) for c in calls)
        end_ts = max(float(c.get("end_ts") or 0) for c in calls)
        parent_tool = delegate_parent.get(agent_id)
        parent_call_id = root_parent
        if parent_tool:
            tool_rec = next((r for r in records if r.get("call_id") == parent_tool), None)
            if tool_rec and tool_rec.get("parent_call_id"):
                parent_call_id = tool_rec["parent_call_id"]
        call_id = f"agent-exec-{agent_id}"
        synth.append({
            "call_id": call_id,
            "parent_call_id": parent_call_id,
            "_has_ids": True,
            "call_type": "AgentCall",
            "level": "agent",
            "agent_id": agent_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "input": "",
            "output": "",
            "label": agent_id,
            "tool_name": "",
            "model": "",
            "thinking": "",
            "processing_name": "",
            "_synthetic": True,
        })
        for c in calls:
            if not c.get("parent_call_id"):
                c["parent_call_id"] = call_id

    return synth


def _synthesize_context_contributions(
    kg: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rebuild ``context_part_contributed`` events from KG ContextContribution nodes."""
    nodes = kg.get("nodes", [])
    edges = kg.get("edges", [])
    nodes_by_id = {n.get("id", ""): n for n in nodes}

    llm_by_id = {
        r["call_id"]: r
        for r in records
        if r.get("call_type") == "LLMCall" and r.get("call_id")
    }
    for node in nodes:
        if node.get("node_type") != "LLMCall":
            continue
        cid = node.get("callId") or node.get("id", "")
        nid = node.get("id", "")
        if cid and cid not in llm_by_id:
            # Align shorthand ids (llm-N) with record call_ids when present.
            match = next((r for r in records if r.get("call_id") == cid), None)
            if match:
                llm_by_id[cid] = match
        if nid and nid not in llm_by_id:
            match = next((r for r in records if r.get("call_id") == nid), None)
            if match:
                llm_by_id[nid] = match

    # contributesTo: ContextContribution → LLMCall
    cc_to_llm: dict[str, str] = {}
    for edge in edges:
        if (edge.get("edge_type") or edge.get("type")) != "contributesTo":
            continue
        src = edge.get("source") or edge.get("from_id") or ""
        tgt = edge.get("target") or edge.get("to_id") or ""
        if src.startswith("cpr-") or nodes_by_id.get(src, {}).get("node_type") == "ContextContribution":
            tgt_node = nodes_by_id.get(tgt, {})
            if tgt_node.get("node_type") == "LLMCall":
                llm_id = tgt_node.get("callId") or tgt_node.get("id") or tgt
            else:
                llm_id = tgt
            cc_to_llm[src] = llm_id

    events: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("node_type") != "ContextContribution":
            continue
        cc_id = node.get("id", "")
        llm_id = cc_to_llm.get(cc_id, "")
        llm_rec = llm_by_id.get(llm_id)
        agent_id = node.get("agentId") or (llm_rec or {}).get("agent_id", "")
        ts = float(node.get("timestamp") or node.get("startTime") or 0)
        if llm_rec and not ts:
            ts = float(llm_rec.get("start_ts") or 0)

        events.append({
            "kind": "context_part_contributed",
            "timestamp": ts,
            "agent_id": agent_id,
            "llm_call_id": llm_id or None,
            "part_id": node.get("partId") or node.get("id", ""),
            "source": node.get("source") or node.get("sectionId") or "?",
            "access_mechanism": node.get("accessMechanism") or node.get("mechanism") or "inject",
            "cause_type": node.get("causeType") or "deterministic",
            "token_estimate": node.get("tokenEstimate") or 0,
            "retained": node.get("retained", True),
            "content": node.get("content") or "",
            "content_preview": node.get("contentPreview") or node.get("content") or "",
            "placement": node.get("sectionId") or "",
        })

    return events


# Reverse of normalizer _ANN_KEY_MAP for plot event synthesis.
_ANN_CAMEL_TO_SNAKE: dict[str, str] = {
    "sourceAgentId": "source_agent_id",
    "targetAgentId": "target_agent_id",
    "task": "task",
    "correlationId": "correlation_id",
    "status": "status",
    "segments": "segments",
    "totalTokens": "total_tokens",
    "operation": "operation",
    "target": "target",
    "messageType": "message_type",
    "policyId": "policy_id",
}


def _synthesize_annotation_events(kg: dict[str, Any]) -> list[dict[str, Any]]:
    """Rebuild point-in-time annotation events from CallAnnotation KG nodes."""
    events: list[dict[str, Any]] = []
    for node in kg.get("nodes", []):
        if node.get("node_type") != "CallAnnotation":
            continue
        kind = node.get("kind") or node.get("annotationKind") or ""
        if not kind:
            continue
        ev: dict[str, Any] = {
            "kind": kind,
            "timestamp": float(node.get("timestamp") or node.get("startTime") or 0),
            "agent_id": node.get("agentId") or "",
        }
        if node.get("callId"):
            ev["call_id"] = node["callId"]
        if node.get("parentCallId"):
            ev["parent_call_id"] = node["parentCallId"]
        for camel, snake in _ANN_CAMEL_TO_SNAKE.items():
            if node.get(camel) is not None:
                ev[snake] = node[camel]
        if node.get("toolName"):
            ev["tool_name"] = node["toolName"]
        events.append(ev)
    return events


def _kg_to_plot_inputs(
    kg: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reconstruct plotter inputs from kg.json using the same path as events.jsonl."""
    from mas.lab.plots.multilevel_trajectory.records import _build_call_records

    plot_events = (kg.get("meta") or {}).get("plot_events")
    if plot_events:
        events = [dict(e) for e in plot_events]
        _normalize_timestamps([], events)
        records = _build_call_records(events)
        records.sort(key=lambda r: r["start_ts"])
        return records, events

    events = kg_to_events(kg)
    events.extend(_synthesize_annotation_events(kg))
    provisional = _build_call_records([dict(e) for e in events])
    events.extend(_synthesize_context_contributions(kg, provisional))
    _normalize_timestamps([], events)
    records = _build_call_records(events)
    records.sort(key=lambda r: r["start_ts"])
    events.sort(key=lambda e: float(e.get("timestamp") or 0))
    return records, events


def kg_to_events(kg: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert kg.json into a flat event list for plotters that expect events.

    Synthesizes minimal ``*_start`` / ``*_end`` event pairs from call nodes,
    plus ``routing`` / ``routing_result`` events from routing edges. This is
    a compatibility shim so that existing plotter code (``_extract_delegations``,
    ``_extract_agent_order``, ``_extract_user_frame``) works unchanged.
    """
    nodes = kg.get("nodes", [])
    edges = kg.get("edges", [])
    events: list[dict[str, Any]] = []
    nodes_by_id: dict[str, dict] = {n.get("id", ""): n for n in nodes}

    # -- Routing edges → routing + routing_result event pairs --
    route_seq = 0
    for edge in edges:
        etype = edge.get("edge_type", "") or edge.get("type", "")
        if etype != "callsAgent":
            continue
        src_id = edge.get("source", "")
        tgt_id = edge.get("target", "")
        src_node = nodes_by_id.get(src_id, {})
        tgt_node = nodes_by_id.get(tgt_id, {})
        cid = f"route-{route_seq}"
        route_seq += 1
        events.append({
            "kind": "routing",
            "timestamp": float(src_node.get("startTime") or 0),
            "source_agent_id": src_node.get("agentId", ""),
            "target_agent_id": tgt_node.get("agentId") or tgt_node.get("agentName", ""),
            "task": src_node.get("inputContent") or src_node.get("toolArguments", ""),
            "correlation_id": cid,
        })
        events.append({
            "kind": "routing_result",
            "timestamp": float(src_node.get("endTime") or 0),
            "source_agent_id": src_node.get("agentId", ""),
            "target_agent_id": tgt_node.get("agentId") or tgt_node.get("agentName", ""),
            "status": src_node.get("status", "success"),
            "correlation_id": cid,
        })

    # Also synthesize routing from contains edges between AgentCalls
    for edge in edges:
        etype = edge.get("edge_type", "") or edge.get("type", "")
        if etype != "contains":
            continue
        src_node = nodes_by_id.get(edge.get("source", ""), {})
        tgt_node = nodes_by_id.get(edge.get("target", ""), {})
        if src_node.get("node_type") == "AgentCall" and tgt_node.get("node_type") == "AgentCall":
            cid = f"route-{route_seq}"
            route_seq += 1
            events.append({
                "kind": "routing",
                "timestamp": float(tgt_node.get("startTime") or 0),
                "source_agent_id": src_node.get("agentId", ""),
                "target_agent_id": tgt_node.get("agentId", ""),
                "task": tgt_node.get("inputContent", ""),
                "correlation_id": cid,
            })
            events.append({
                "kind": "routing_result",
                "timestamp": float(tgt_node.get("endTime") or 0),
                "source_agent_id": src_node.get("agentId", ""),
                "target_agent_id": tgt_node.get("agentId", ""),
                "status": tgt_node.get("status", "success"),
                "correlation_id": cid,
            })

    # -- Call nodes → start/end event pairs --
    _TYPE_TO_KIND: dict[str, str] = {
        "AgentCall":      "execution",
        "MASCall":        "mas_call",
        "LLMCall":        "llm_call",
        "ToolCall":       "tool_call",
        "SkillCall":      "skill_execution",
        "ProcessingCall": "processing",
        "ThinkingCall":   "thinking",
        "MITMCall":       "processing",
    }

    for node in nodes:
        ntype = node.get("node_type", "")
        kind_base = _TYPE_TO_KIND.get(ntype)
        if kind_base is None:
            continue

        call_id = node.get("callId") or node.get("id", "")
        # Skip orphan shorthand nodes and KG-only synthesized processing gates.
        if ntype in {"LLMCall", "ToolCall", "ProcessingCall", "SkillCall"}:
            if node.get("startTime") is None:
                continue
        if ntype == "ProcessingCall" and str(call_id).startswith("synth-pc-"):
            continue

        agent_id = node.get("agentId") or node.get("agentName", "")
        parent_call_id = node.get("parentCallId")

        # Start event
        start_ev: dict[str, Any] = {
            "kind": f"{kind_base}_start",
            "timestamp": float(node.get("startTime") or 0),
            "agent_id": agent_id,
            "call_id": call_id,
            "parent_call_id": parent_call_id,
        }

        # End event
        end_ev: dict[str, Any] = {
            "kind": f"{kind_base}_end",
            "timestamp": float(node.get("endTime") or 0),
            "agent_id": agent_id,
            "call_id": call_id,
            "parent_call_id": parent_call_id,
            "status": node.get("status", "success"),
        }

        if ntype == "AgentCall":
            start_ev["input"] = node.get("inputContent", "")
            # Mark root agent as entry agent
            if not parent_call_id:
                start_ev["context"] = {"is_entry_agent": True}
            end_ev["output"] = node.get("outputContent", "")
            if not parent_call_id:
                end_ev["context"] = {"is_entry_agent": True}

        elif ntype == "MASCall":
            start_ev["mas_name"] = node.get("masName") or node.get("agentId", "")
            end_ev["output"] = node.get("outputContent", "")

        elif ntype == "LLMCall":
            start_ev["model"] = node.get("modelName") or node.get("llmName", "")
            start_ev["messages"] = []  # No raw messages in KG; prompt is in State nodes
            start_ev["prompt"] = node.get("prompt", "")
            end_ev["response"] = {"content": node.get("completion", "")}
            end_ev["output"] = node.get("completion", "")
            thinking = node.get("thinking", "")
            if thinking:
                end_ev["thinking"] = thinking

        elif ntype == "ToolCall":
            start_ev["tool_name"] = node.get("toolName", "")
            start_ev["arguments"] = node.get("toolArguments", "")
            end_ev["tool_name"] = node.get("toolName", "")
            end_ev["result"] = node.get("toolOutput", "")

        elif ntype == "SkillCall":
            start_ev["skill_name"] = node.get("skillName", "")
            start_ev["input"] = node.get("skillInput", "")
            end_ev["output"] = node.get("skillOutput", "")

        elif ntype == "ProcessingCall":
            start_ev["processing_name"] = node.get("processingName", "")
            start_ev["processing_type"] = node.get("processingType", "")
            end_ev["processing_output"] = node.get("outputContent", "")

        events.extend([start_ev, end_ev])

    events.sort(key=lambda e: float(e.get("timestamp") or 0))
    return events


# ---------------------------------------------------------------------------
# KGView — faceted access layer over call records
# ---------------------------------------------------------------------------

class KGView:
    """Lightweight faceted access layer over a kg.json call-record set.

    Inspired by the ``dataquery.Store`` pattern:

    * ``query(call_type, **field_filters)`` — filter records by type and field
      equality (case-insensitive for strings).
    * ``get(call_id)`` — O(1) lookup by ``call_id``.

    All records use the normalized snake_case field names produced by
    :func:`kg_to_call_records`:

        call_id, parent_call_id, call_type, level,
        agent_id, start_ts, end_ts, label, tool_name, model, …

    Usage
    -----
    ::

        view = KGView.from_kg(kg)                     # build from kg dict
        llm_calls = view.query("LLMCall")              # all LLM calls (sorted by start_ts)
        root_agents = view.query("AgentCall", parent_call_id=None)
        parent = view.get(record["parent_call_id"])   # O(1) parent lookup
    """

    def __init__(self, records: list[dict[str, Any]]) -> None:
        from collections import defaultdict

        # Preserve insertion order within each type (already sorted by start_ts
        # from kg_to_call_records).
        self._by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._by_id: dict[str, dict[str, Any]] = {}

        for r in records:
            self._by_type[r.get("call_type", "")].append(r)
            cid = r.get("call_id", "")
            if cid:
                self._by_id[cid] = r

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_kg(cls, kg: dict[str, Any]) -> "KGView":
        """Build a KGView from a raw kg.json dict."""
        return cls(kg_to_call_records(kg))

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def query(
        self,
        call_type: str,
        **field_filters: Any,
    ) -> list[dict[str, Any]]:
        """Return records of *call_type* matching *field_filters*.

        Each keyword argument is an equality filter.  String comparisons are
        case-insensitive.  Pass no filters to retrieve all records of that type.
        Records are returned in ascending ``start_ts`` order.

        Examples::

            view.query("LLMCall")
            view.query("AgentCall", parent_call_id=None)
            view.query("ToolCall", agent_id="sre")
        """
        records = self._by_type.get(call_type, [])
        if not field_filters:
            return list(records)

        def _match(record: dict[str, Any]) -> bool:
            for k, v in field_filters.items():
                rv = record.get(k)
                if v is None:
                    if rv not in (None, ""):
                        return False
                elif isinstance(v, str):
                    if str(rv or "").lower() != v.lower():
                        return False
                else:
                    if rv != v:
                        return False
            return True

        return [r for r in records if _match(r)]

    def get(self, call_id: str | None) -> "dict[str, Any] | None":
        """Return the record with *call_id*, or ``None`` if not found."""
        if not call_id:
            return None
        return self._by_id.get(call_id)

    def types(self) -> list[str]:
        """Return the call_type names present in this view."""
        return list(self._by_type.keys())


# ---------------------------------------------------------------------------
# FacetQuery — filter spec for KG-backed trajectory queries
# ---------------------------------------------------------------------------

@dataclass
class FacetQuery:
    """Lightweight filter spec for KG-backed trajectory queries.

    Python port of the JavaScript FacetBrowser ``TransformState``.  All fields
    are optional (``None`` = no filter on that dimension).  The dataclass is
    JSON-serialisable via :meth:`to_dict` / :meth:`from_dict` so it can be
    transported over WebSocket between the JS UI and the Python backend.

    Examples
    --------
    ::

        # All calls for a single session
        q = FacetQuery(session_id="abc-123")

        # Only LLM and Tool calls for two agents
        q = FacetQuery(agent_ids=["orchestrator", "analyst"],
                       call_types=["LLMCall", "ToolCall"])

        # Time slice (Unix timestamps)
        q = FacetQuery(time_range=(1716000000.0, 1716000010.0))

        # From a JS TransformState-shaped dict (WebSocket payload)
        q = FacetQuery.from_dict(ws_payload)
    """

    session_id:  str | None = None
    run_id:      str | None = None
    agent_ids:   list[str] | None = field(default=None)
    call_types:  list[str] | None = field(default=None)
    time_range:  tuple[float, float] | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FacetQuery":
        """Deserialise from a JSON-compatible dict (e.g. JS TransformState).

        Unknown keys are silently ignored so future JS fields don't break
        the Python decoder.
        """
        tr = d.get("time_range") or d.get("timeRange")
        return cls(
            session_id  = d.get("session_id") or d.get("sessionId"),
            run_id      = d.get("run_id")      or d.get("runId"),
            agent_ids   = d.get("agent_ids")   or d.get("agentIds"),
            call_types  = d.get("call_types")  or d.get("callTypes"),
            time_range  = tuple(tr) if tr and len(tr) == 2 else None,
        )


# ---------------------------------------------------------------------------
# KGSource — high-level data source: KG + FacetQuery → (records, events)
# ---------------------------------------------------------------------------

class KGSource:
    """High-level data source backed by a kg.json dict (or file path).

    Applies a :class:`FacetQuery` filter and returns the ``(records, events)``
    tuple expected by the plotters::

        source = KGSource(kg)                        # from dict
        source = KGSource.from_file("path/to/kg.json")

        records, events = source.load()              # unfiltered
        records, events = source.load(FacetQuery(   # filtered
            agent_ids=["orchestrator"],
            call_types=["LLMCall", "ToolCall"],
        ))

    The ``records`` list uses the normalised ``snake_case`` format produced by
    :func:`kg_to_call_records` (same as ``_build_call_records`` output).
    The ``events`` list contains synthetic ``*_start`` / ``*_end`` events from
    :func:`kg_to_events` — required by annotation/CPR extraction helpers in
    :mod:`multilevel_trajectory`.

    Sub-classing
    ------------
    Override :meth:`_fetch_kg` to change the data source (e.g. live Neo4j
    fetch).  The filtering logic in :meth:`load` applies universally.

    Future: WebSocket streaming
    ---------------------------
    A WebSocket endpoint wraps this class: it deserialises the JS
    ``TransformState`` payload into a ``FacetQuery``, calls ``source.load(q)``,
    serialises the result, and streams it back to the browser.  No change to
    the Python plotter code is required.
    """

    def __init__(
        self,
        kg: dict[str, Any],
        *,
        kg_path: Path | None = None,
    ) -> None:
        self._kg = kg
        self._kg_path = kg_path.resolve() if kg_path else None

    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
    ) -> "KGSource":
        """Load a kg.json file and return a :class:`KGSource`."""
        resolved = Path(path).expanduser().resolve()
        return cls(load_kg(resolved), kg_path=resolved)

    # ------------------------------------------------------------------
    # Overridable data fetch (hook for Neo4j / live sources)
    # ------------------------------------------------------------------

    def _fetch_kg(self) -> dict[str, Any]:
        """Return the raw KG dict.  Override in subclasses for live sources."""
        return self._kg

    # ------------------------------------------------------------------
    # Public load interface
    # ------------------------------------------------------------------

    def load(
        self,
        query: FacetQuery | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return ``(call_records, events)`` filtered by *query*.

        Both lists use the same format consumed by
        :func:`~mas.lab.plots.multilevel_trajectory.plot_multilevel_trajectory`.
        When *query* is ``None`` or all-``None``, the full KG is returned.
        """
        kg = self._fetch_kg()
        records, events = _kg_to_plot_inputs(kg)

        if query is None:
            return records, events

        # Apply session / run filters (attributes propagated by denormalize)
        if query.session_id:
            sid = query.session_id.lower()
            nodes_by_id: dict[str, dict] = {
                n.get("id", ""): n for n in kg.get("nodes", [])
            }
            # Filter records to those whose KG node carries the matching sessionId
            allowed_ids: set[str] = {
                n.get("id", "")
                for n in kg.get("nodes", [])
                if str(n.get("sessionId") or "").lower() == sid
            }
            records = [r for r in records if r.get("call_id", "") in allowed_ids]
            events  = [e for e in events  if e.get("call_id", "") in allowed_ids
                       or e.get("correlation_id", "").startswith("route-")]

        if query.run_id:
            rid = query.run_id.lower()
            records = [r for r in records if str(r.get("run_id") or "").lower() == rid]

        if query.agent_ids:
            allowed = {a.lower() for a in query.agent_ids}
            records = [r for r in records if r.get("agent_id", "").lower() in allowed]
            events  = [e for e in events  if e.get("agent_id", "").lower() in allowed
                       or e.get("kind", "").startswith("routing")]

        if query.call_types:
            allowed_ct = set(query.call_types)
            records = [r for r in records if r.get("call_type", "") in allowed_ct]

        if query.time_range:
            t0, t1 = query.time_range
            records = [r for r in records if r.get("end_ts", 0) >= t0
                       and r.get("start_ts", 0) <= t1]
            events  = [e for e in events
                       if float(e.get("timestamp") or 0) >= t0
                       and float(e.get("timestamp") or 0) <= t1]

        return records, events

    def stream(
        self,
        query: "FacetQuery | None" = None,
    ) -> "Iterator[KGStreamChunk]":
        """Stream ``(records, events)`` as typed chunks — unified interface for
        both the pipeline path and the WebSocket/UI path.

        Currently yields a **single chunk** containing the full filtered dataset
        (``done=True``).  Future implementations (live Neo4j, windowed delivery)
        will yield multiple incremental chunks before the final ``done=True``
        terminator.

        Both the pipeline step and the WebSocket handler in the tutorial server
        consume this iterator identically::

            for chunk in source.stream(query):
                # render or accumulate
                if chunk["done"]:
                    break

        Parameters
        ----------
        query:
            Optional :class:`FacetQuery`.  ``None`` = no filter.

        Yields
        ------
        KGStreamChunk
            A typed dict: ``{"records": list, "events": list, "done": bool}``.
        """
        records, events = self.load(query)
        if not records:
            logger.warning(
                "KGSource.stream(): load() returned 0 records "
                "(query=%r). Yielding empty terminal chunk.",
                query,
            )
        yield KGStreamChunk(records=records, events=events, done=True)
