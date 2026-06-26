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
        "LLMCall":        "llm_call",
        "ToolCall":       "tool_call",
        "ProcessingCall": "processing",
        "ThinkingCall":   "thinking",
        "MITMCall":       "processing",
    }

    for node in nodes:
        ntype = node.get("node_type", "")
        kind_base = _TYPE_TO_KIND.get(ntype)
        if kind_base is None:
            continue

        agent_id = node.get("agentId") or node.get("agentName", "")
        call_id = node.get("callId") or node.get("id", "")
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

    def __init__(self, kg: dict[str, Any]) -> None:
        self._kg = kg

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "KGSource":
        """Load a kg.json file and return a :class:`KGSource`."""
        return cls(load_kg(path))

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
        records = kg_to_call_records(kg)
        events  = kg_to_events(kg)

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
