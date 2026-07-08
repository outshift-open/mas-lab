#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Multi-agent topology extraction for the ``.graph`` span.

Observation tools (and the IOA Observe SDK's ``@graph`` decorator) expect a span of kind
``graph`` — named ``<app>.graph`` — carrying the multi-agent topology as JSON on
``gen_ai.ioa.graph``, plus ``gen_ai.ioa.graph_dynamism`` and
``gen_ai.ioa.graph_determinism_score``.  Without it, the agent graph cannot
be rendered and topology-dependent processing fails.

Topology is derived from the native event stream: nodes = observed agents,
edges = ``source_agent_id → target_agent_id`` handoffs (routing / communication).
"""
from __future__ import annotations

import json
from typing import Any

GRAPH_ATTR = "gen_ai.ioa.graph"
GRAPH_PROTOCOL_ATTR = "gen_ai.ioa.graph.protocol"
GRAPH_DYNAMISM_ATTR = "gen_ai.ioa.graph_dynamism"
GRAPH_DETERMINISM_ATTR = "gen_ai.ioa.graph_determinism_score"
OBSERVE_SPAN_KIND_ATTR = "ioa_observe.span.kind"


def build_topology(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a ``{"nodes": [...], "edges": [...]}`` topology from native events."""
    spec = next((e for e in events if e.get("kind") == "system_specification"), None)
    agents: set[str] = set()
    edges: dict[tuple[str, str], dict[str, Any]] = {}

    if spec:
        for a in spec.get("agents") or spec.get("agent_ids") or []:
            aid = a.get("id") or a.get("name") if isinstance(a, dict) else a
            if aid:
                agents.add(str(aid))

    for ev in events:
        kind = str(ev.get("kind") or "")
        agent = ev.get("agent_id")
        if agent and kind.startswith(("execution", "mas_call")):
            agents.add(str(agent))
        src = ev.get("source_agent_id")
        tgt = ev.get("target_agent_id") or ev.get("selected_agent")
        if src and tgt:
            agents.add(str(src))
            agents.add(str(tgt))
            key = (str(src), str(tgt))
            edges.setdefault(key, {
                "source": str(src),
                "target": str(tgt),
                "kind": "communication" if kind.startswith("agent_communication") else "routing",
                "conditional": kind in ("routing", "routing_result"),
            })

    return {
        "nodes": [{"id": a, "name": a} for a in sorted(agents)],
        "edges": [edges[k] for k in sorted(edges)],
    }


def graph_span_attributes(topology: dict[str, Any], *, protocol: str = "MAS") -> dict[str, Any]:
    """OTel attributes for a ``graph`` span from a *topology* dict."""
    return {
        OBSERVE_SPAN_KIND_ATTR: "graph",
        GRAPH_ATTR: json.dumps(topology, sort_keys=True, ensure_ascii=True),
        GRAPH_PROTOCOL_ATTR: protocol,
        GRAPH_DYNAMISM_ATTR: topology_dynamism(topology),
        GRAPH_DETERMINISM_ATTR: determinism_score(topology),
    }


def topology_dynamism(topology: dict[str, Any]) -> str:
    edges = topology.get("edges") or []
    return "dynamic" if any(e.get("conditional") for e in edges) else "static"


def determinism_score(topology: dict[str, Any]) -> float:
    edges = topology.get("edges") or []
    if not edges:
        return 1.0
    return round(sum(1 for e in edges if not e.get("conditional")) / len(edges), 4)


def has_topology(topology: dict[str, Any]) -> bool:
    return bool(topology.get("nodes"))


def derive_app_name(events: list[dict[str, Any]], fallback: str = "") -> str:
    """Best-effort application name from the event stream.

    Fixes the "everything defaults to mas-runtime" bug: callers that don't pass an
    explicit app name get the real one from the trace; explicit always overrides.
    """
    for ev in events:
        for key in ("app_name", "application", "app", "application_id"):
            if ev.get(key):
                return str(ev[key])
        meta = ev.get("metadata")
        if isinstance(meta, dict):
            for key in ("app_name", "application", "app"):
                if meta.get(key):
                    return str(meta[key])
        if ev.get("kind") == "system_specification" and (ev.get("name") or ev.get("app_name")):
            return str(ev.get("name") or ev.get("app_name"))
    return fallback


__all__ = [
    "build_topology",
    "graph_span_attributes",
    "topology_dynamism",
    "determinism_score",
    "has_topology",
    "derive_app_name",
]
