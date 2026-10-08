#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Multi-agent topology extraction for the ``.graph`` span.

OXP (and the IOA Observe SDK's ``@graph`` decorator) expect a span of kind
``graph`` — named ``<app>.graph`` — carrying the multi-agent topology as JSON on
``gen_ai.ioa.graph``, plus ``gen_ai.ioa.graph_dynamism`` and
``gen_ai.ioa.graph_determinism_score``.  Without it, OXP cannot render the
agent graph and topology-dependent processing fails.

The MAS native export historically emitted no such span (only ``mas.*`` boundary
spans), which is the gap this module fills.  Reference contract:
``thirdparty/observe`` — ``ioa_observe.sdk.decorators`` (``@graph``) and
``gen_ai.ioa.graph*`` attributes.

Topology is derived from the native event stream:

* **nodes** — the distinct agents observed (``execution`` / ``AgentCall`` events,
  plus any agent referenced as a routing/communication endpoint), or the agents
  declared by a ``system_specification`` event when present.
* **edges** — ``source_agent_id → target_agent_id`` from ``routing`` /
  ``routing_result`` / ``agent_communication`` events, plus parent→child agent
  delegations inferred from the call tree.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

# Observe / OXP span-attribute keys (thirdparty/observe: ioa_observe SDK).
from mas.library.telemetry.conversion import semconv

GRAPH_ATTR = semconv.GEN_AI_IOA_GRAPH
GRAPH_PROTOCOL_ATTR = semconv.GEN_AI_IOA_GRAPH_PROTOCOL
GRAPH_DYNAMISM_ATTR = semconv.GEN_AI_IOA_GRAPH_DYNAMISM
GRAPH_DETERMINISM_ATTR = semconv.GEN_AI_IOA_GRAPH_DETERMINISM
OBSERVE_SPAN_KIND_ATTR = semconv.IOA_SPAN_KIND

_ROUTING_KINDS = {
    "routing",
    "routing_result",
    "agent_communication_start",
    "agent_communication_end",
}

_GENERIC_AGENT_IDS = frozenset({"", "unknown", "agent", "mas"})


def _real_agent(agent_id: str) -> bool:
    return bool(agent_id) and agent_id not in _GENERIC_AGENT_IDS


def build_topology(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a ``{"nodes": [...], "edges": [...]}`` topology from native events.

    Node ids are agent ids; edges are directed ``source → target`` handoffs.
    Deterministic ordering (sorted) so repeated runs produce identical JSON.
    """
    # A declared spec, if the runtime emitted one, wins for the node set.
    spec = _find_system_specification(events)

    agents: set[str] = set()
    edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
    call_agent: Dict[str, str] = {}

    if spec:
        for a in _spec_agents(spec):
            if _real_agent(a):
                agents.add(a)

    for ev in events:
        kind = str(ev.get("kind") or "")
        agent = ev.get("agent_id")
        if agent and _real_agent(str(agent)):
            if kind.startswith(("execution", "mas_call")) or kind in {
                "llm_call_start",
                "tool_call_start",
            }:
                agents.add(str(agent))
        cid = str(ev.get("call_id") or "").strip()
        if cid and agent and _real_agent(str(agent)) and kind.endswith("_start"):
            call_agent[cid] = str(agent)
        src = ev.get("source_agent_id")
        tgt = ev.get("target_agent_id") or ev.get("selected_agent")
        if src and tgt and _real_agent(str(src)) and _real_agent(str(tgt)):
            agents.add(str(src))
            agents.add(str(tgt))
            key = (str(src), str(tgt))
            edges.setdefault(
                key,
                {
                    "source": str(src),
                    "target": str(tgt),
                    "kind": _edge_kind(kind),
                    "conditional": kind in ("routing", "routing_result"),
                },
            )

    for ev in events:
        if str(ev.get("kind") or "") != "execution_start":
            continue
        child = str(ev.get("agent_id") or "")
        parent_id = str(ev.get("parent_call_id") or "")
        if not child or not parent_id or not _real_agent(child):
            continue
        parent_agent = call_agent.get(parent_id)
        if parent_agent is None:
            for cid, aid in call_agent.items():
                if cid.endswith(parent_id) or parent_id in cid:
                    parent_agent = aid
                    break
        if parent_agent and parent_agent != child and _real_agent(parent_agent):
            agents.add(child)
            agents.add(parent_agent)
            key = (parent_agent, child)
            edges.setdefault(
                key,
                {
                    "source": parent_agent,
                    "target": child,
                    "kind": "handoff",
                    "conditional": False,
                },
            )

    nodes = [{"id": a, "name": a} for a in sorted(agents)]
    edge_list = [edges[k] for k in sorted(edges)]
    return {"nodes": nodes, "edges": edge_list}


def graph_span_attributes(
    topology: Dict[str, Any],
    *,
    protocol: str = "MAS",
) -> Dict[str, Any]:
    """Build the OTel attributes for a ``graph`` span from a *topology* dict.

    OXP ``norm`` requires ``nodes`` to be a dict keyed by node id (not a list).
    """
    payload = dict(topology)
    nodes = payload.get("nodes")
    if isinstance(nodes, list):
        payload["nodes"] = {
            str(n.get("id") or n.get("name")): n
            for n in nodes
            if isinstance(n, dict) and (n.get("id") or n.get("name"))
        }
    return {
        OBSERVE_SPAN_KIND_ATTR: "graph",
        GRAPH_ATTR: json.dumps(payload, sort_keys=True, ensure_ascii=True),
        GRAPH_PROTOCOL_ATTR: protocol,
        GRAPH_DYNAMISM_ATTR: topology_dynamism(topology),
        GRAPH_DETERMINISM_ATTR: determinism_score(topology),
    }


def topology_dynamism(topology: Dict[str, Any]) -> float:
    """Observe-sdk ``topology_dynamism``: conditional_edges / total_edges."""
    edges = topology.get("edges") or []
    if not edges:
        return 0.0
    conditional = sum(1 for e in edges if e.get("conditional"))
    return conditional / len(edges)


def determinism_score(topology: Dict[str, Any]) -> float:
    """Observe-sdk ``determinism_score``: 1 - dynamism (1.0 = fully deterministic)."""
    return 1.0 - topology_dynamism(topology)


def has_topology(topology: Dict[str, Any]) -> bool:
    """Whether a topology has anything worth emitting a graph span for."""
    return bool(topology.get("nodes"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _edge_kind(event_kind: str) -> str:
    if event_kind.startswith("agent_communication"):
        return "communication"
    return "routing"


def _find_system_specification(
    events: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for ev in events:
        if ev.get("kind") == "system_specification":
            return ev
    return None


def _spec_agents(spec: Dict[str, Any]) -> List[str]:
    agents = spec.get("agents") or spec.get("agent_ids") or []
    out: List[str] = []
    for a in agents:
        if isinstance(a, dict):
            aid = a.get("id") or a.get("name")
            if aid:
                out.append(str(aid))
        elif a:
            out.append(str(a))
    return out


def require_mas_name(*candidates: str) -> str:
    """Return the first non-empty MAS name, or raise.

    The MAS name is mandatory. There is no hardcoded default.
    """
    for raw in candidates:
        name = str(raw or "").strip()
        if name:
            return name
    raise ValueError(
        "MAS app name is required: pass --app-name or set app_name on the events"
    )


def derive_app_name(events: List[Dict[str, Any]], fallback: str = "") -> str:
    """Best-effort application name from the event stream.

    Looks for an explicit app name on any event (``app_name`` / ``mas_id`` /
    ``application`` / ``app`` / ``metadata.app_name``), or a
    ``system_specification`` event's ``name`` / ``app_name``.  Returns
    *fallback* when none is found.
    """
    for ev in events:
        for key in ("app_name", "mas_id", "application", "app", "application_id"):
            val = ev.get(key)
            if val:
                return str(val)
        meta = ev.get("metadata")
        if isinstance(meta, dict):
            for key in ("app_name", "application", "app"):
                raw = meta.get(key)
                if raw:
                    return str(raw)
        if ev.get("kind") == "system_specification":
            name = ev.get("name") or ev.get("app_name")
            if name:
                return str(name)
    return fallback


__all__ = [
    "build_topology",
    "graph_span_attributes",
    "topology_dynamism",
    "determinism_score",
    "has_topology",
    "require_mas_name",
    "derive_app_name",
    "GRAPH_ATTR",
    "GRAPH_PROTOCOL_ATTR",
    "GRAPH_DYNAMISM_ATTR",
    "GRAPH_DETERMINISM_ATTR",
    "OBSERVE_SPAN_KIND_ATTR",
]
