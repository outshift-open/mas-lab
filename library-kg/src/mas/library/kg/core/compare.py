#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""KG structural comparison.

Pure functions — no PipelineStep or I/O dependency.
Uses only stdlib (collections, logging).

Public API
----------
compare_kg(candidate, reference, *, strict) → KGCompareResult
Individual check functions are also public for targeted use.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "KGCompareResult",
    "compare_kg",
    "check_agent_coverage",
    "check_node_distribution",
    "check_edge_distribution",
    "check_call_depth",
    "check_tool_coverage",
    "check_delegation_topology",
    "check_element_diff",
    "_element_level_diff",
]

# Fields that are volatile (IDs, timestamps) and should not be compared.
_VOLATILE_FIELDS = frozenset(
    {
        "id",
        "callId",
        "parentCallId",
        "spanId",
        "traceId",
        "sourceRecordIds",
        "runId",
        "sessionId",
        "executionId",
        "sourceCallId",
        "stateNodeId",
        "fromState",
        "toState",
        "annotationId",
        "transitionId",
        "transitionTimestamp",
        "transitionDuration",
        "realizesCallId",
        "contentHash",
        "timestamp",
        "startTime",
        "endTime",
        "durationMs",
        "segments",
        "totalTokens",
        # legacy snake_case variants
        "call_id",
        "parent_call_id",
        "span_id",
        "trace_id",
        "run_id",
        "session_id",
        "start_time",
        "end_time",
        "duration_ms",
    }
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class KGCompareResult:
    """Result of a KG structural comparison."""

    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    reference_stats: Dict[str, Any] = field(default_factory=dict)
    candidate_stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "summary": self.summary,
            "reference_stats": self.reference_stats,
            "candidate_stats": self.candidate_stats,
        }


# ---------------------------------------------------------------------------
# Field extraction helpers (multi-format)
# ---------------------------------------------------------------------------


def _node_type(node: Dict[str, Any]) -> str:
    for key in ("node_type", "nodeType", "type"):
        val = node.get(key)
        if val:
            return str(val)
    return "unknown"


def _edge_type(edge: Dict[str, Any]) -> str:
    for key in ("edge_type", "edgeType", "type"):
        val = edge.get(key)
        if val:
            return str(val)
    return "unknown"


def _edge_source(edge: Dict[str, Any]) -> str:
    return str(edge.get("from_id") or edge.get("source") or edge.get("from") or "")


def _edge_target(edge: Dict[str, Any]) -> str:
    return str(edge.get("to_id") or edge.get("target") or edge.get("to") or "")


def _agent_ids(nodes: List[Dict[str, Any]]) -> Set[str]:
    ids: Set[str] = set()
    for n in nodes:
        aid = n.get("agentId") or n.get("agent_id")
        if aid:
            ids.add(str(aid))
    return ids


def _tool_names(nodes: List[Dict[str, Any]]) -> Set[str]:
    names: Set[str] = set()
    for n in nodes:
        if _node_type(n) == "ToolCall":
            tn = n.get("toolName") or n.get("tool_name")
            if tn:
                names.add(str(tn))
    return names


def _delegation_pairs(
    edges: List[Dict[str, Any]], nodes: List[Dict[str, Any]]
) -> Set[Tuple[str, str]]:
    """Extract (source_agent, target_agent) delegation pairs from callsAgent edges."""
    node_map: Dict[str, str] = {}
    for n in nodes:
        nid = n.get("id", "")
        aid = n.get("agentId") or n.get("agent_id") or ""
        if nid and aid:
            node_map[nid] = str(aid)

    pairs: Set[Tuple[str, str]] = set()
    for e in edges:
        if _edge_type(e) in ("callsAgent", "delegates_to"):
            src = node_map.get(_edge_source(e), "")
            tgt = node_map.get(_edge_target(e), "")
            if src and tgt and src != tgt:
                pairs.add((src, tgt))
    return pairs


def _max_nesting_depth(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> int:
    """Compute maximum containment nesting depth via BFS."""
    from mas.library.kg.core.ontology_align import CONTAINMENT_EDGE_TYPES

    children: Dict[str, List[str]] = {}
    node_ids: Set[str] = {n.get("id", "") for n in nodes}
    for e in edges:
        if _edge_type(e) in CONTAINMENT_EDGE_TYPES:
            src, tgt = _edge_source(e), _edge_target(e)
            if src in node_ids and tgt in node_ids:
                children.setdefault(src, []).append(tgt)

    roots = node_ids - {t for kids in children.values() for t in kids}
    if not roots:
        return 0
    max_d = 0
    stack = [(r, 0) for r in roots]
    while stack:
        nid, depth = stack.pop()
        max_d = max(max_d, depth)
        for child in children.get(nid, []):
            stack.append((child, depth + 1))
    return max_d


def _stable_node_key(node: Dict[str, Any]) -> str:
    """Return a stable identity key for a node (type + non-volatile field hash).

    ``agentId``/``toolName`` lead the key for a human-readable prefix when
    diffing a failing comparison; the trailing hash is what actually
    distinguishes two nodes of the same type/agent/tool but different
    content (e.g. two separate tool calls to the same tool by the same
    agent within one session) in the ``Counter``-based multiset comparison
    this key feeds.
    """
    ntype = _node_type(node)
    agent = node.get("agentId") or node.get("agent_id") or ""
    tool = node.get("toolName") or node.get("tool_name") or ""
    content = {k: v for k, v in node.items() if k not in _VOLATILE_FIELDS}
    content_hash = hashlib.sha256(
        json.dumps(content, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"{ntype}|{agent}|{tool}|{content_hash}"


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_agent_coverage(
    candidate_nodes: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check that candidate contains the same set of agent IDs as reference."""
    ref_agents = _agent_ids(reference_nodes)
    cand_agents = _agent_ids(candidate_nodes)
    missing = ref_agents - cand_agents
    extra = cand_agents - ref_agents
    return {
        "name": "agent_coverage",
        "passed": len(missing) == 0,
        "reference_agents": sorted(ref_agents),
        "candidate_agents": sorted(cand_agents),
        "missing": sorted(missing),
        "extra": sorted(extra),
    }


def check_node_distribution(
    candidate_nodes: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check that candidate has at least as many nodes of each type as reference."""
    ref_dist = Counter(_node_type(n) for n in reference_nodes)
    cand_dist = Counter(_node_type(n) for n in candidate_nodes)
    deficits = {
        ntype: (ref_dist[ntype] - cand_dist.get(ntype, 0))
        for ntype in ref_dist
        if cand_dist.get(ntype, 0) < ref_dist[ntype]
    }
    return {
        "name": "node_distribution",
        "passed": len(deficits) == 0,
        "reference": dict(ref_dist),
        "candidate": dict(cand_dist),
        "deficits": deficits,
    }


def check_edge_distribution(
    candidate_edges: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check that candidate has at least as many edges of each type as reference."""
    ref_dist = Counter(_edge_type(e) for e in reference_edges)
    cand_dist = Counter(_edge_type(e) for e in candidate_edges)
    deficits = {
        etype: (ref_dist[etype] - cand_dist.get(etype, 0))
        for etype in ref_dist
        if cand_dist.get(etype, 0) < ref_dist[etype]
    }
    return {
        "name": "edge_distribution",
        "passed": len(deficits) == 0,
        "reference": dict(ref_dist),
        "candidate": dict(cand_dist),
        "deficits": deficits,
    }


def check_call_depth(
    candidate_nodes: List[Dict[str, Any]],
    candidate_edges: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check that candidate's max call nesting depth ≥ reference."""
    ref_depth = _max_nesting_depth(reference_nodes, reference_edges)
    cand_depth = _max_nesting_depth(candidate_nodes, candidate_edges)
    return {
        "name": "call_depth",
        "passed": cand_depth >= ref_depth,
        "reference_depth": ref_depth,
        "candidate_depth": cand_depth,
    }


def check_tool_coverage(
    candidate_nodes: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check that every tool used in reference appears in candidate."""
    ref_tools = _tool_names(reference_nodes)
    cand_tools = _tool_names(candidate_nodes)
    missing = ref_tools - cand_tools
    return {
        "name": "tool_coverage",
        "passed": len(missing) == 0,
        "reference_tools": sorted(ref_tools),
        "candidate_tools": sorted(cand_tools),
        "missing": sorted(missing),
    }


def check_delegation_topology(
    candidate_nodes: List[Dict[str, Any]],
    candidate_edges: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check that candidate's delegation topology matches reference."""
    ref_pairs = _delegation_pairs(reference_edges, reference_nodes)
    cand_pairs = _delegation_pairs(candidate_edges, candidate_nodes)
    missing = ref_pairs - cand_pairs
    return {
        "name": "delegation_topology",
        "passed": len(missing) == 0,
        "reference": sorted(f"{s}→{t}" for s, t in ref_pairs),
        "candidate": sorted(f"{s}→{t}" for s, t in cand_pairs),
        "missing": sorted(f"{s}→{t}" for s, t in missing),
    }


def check_element_diff(
    candidate_nodes: List[Dict[str, Any]],
    candidate_edges: List[Dict[str, Any]],
    reference_nodes: List[Dict[str, Any]],
    reference_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Node-by-node and edge-by-edge structural diff (volatile fields excluded)."""
    ref_node_keys = Counter(_stable_node_key(n) for n in reference_nodes)
    cand_node_keys = Counter(_stable_node_key(n) for n in candidate_nodes)
    missing_nodes = sorted((ref_node_keys - cand_node_keys).keys())
    spurious_nodes = sorted((cand_node_keys - ref_node_keys).keys())

    def _edge_key(e: Dict[str, Any]) -> str:
        return f"{_edge_type(e)}|{_edge_source(e)}|{_edge_target(e)}"

    ref_edge_keys = Counter(_edge_key(e) for e in reference_edges)
    cand_edge_keys = Counter(_edge_key(e) for e in candidate_edges)
    missing_edges = sorted((ref_edge_keys - cand_edge_keys).keys())
    spurious_edges = sorted((cand_edge_keys - ref_edge_keys).keys())

    identical = (
        not missing_nodes and not spurious_nodes and not missing_edges and not spurious_edges
    )
    return {
        "name": "element_level_diff",
        "passed": identical,
        "missing_nodes": missing_nodes,
        "spurious_nodes": spurious_nodes,
        "missing_edges": missing_edges,
        "spurious_edges": spurious_edges,
    }


# Back-compat alias: same (nodes_a, edges_a, nodes_b, edges_b) signature used by
# the `mas-lab kg` CLI (was mas.lab.graph.steps.compare_kg._element_level_diff).
_element_level_diff = check_element_diff


# ---------------------------------------------------------------------------
# Top-level comparison function
# ---------------------------------------------------------------------------


def compare_kg(
    candidate: Dict[str, Any],
    reference: Dict[str, Any],
    *,
    strict: bool = False,
) -> KGCompareResult:
    """Compare two kg.jsonld documents structurally.

    Args:
        candidate: KG produced by the system under test.
        reference: Ground-truth KG (e.g. from OTel normalization).
        strict:    When True, element_level_diff failures also count as failures.
                   Default False (structural checks 1–6 only).

    Returns:
        :class:`KGCompareResult` with per-check results and overall pass/fail.
    """
    cand_nodes = candidate.get("nodes") or []
    cand_edges = candidate.get("edges") or []
    ref_nodes = reference.get("nodes") or []
    ref_edges = reference.get("edges") or []

    checks: List[Dict[str, Any]] = [
        check_agent_coverage(cand_nodes, ref_nodes),
        check_node_distribution(cand_nodes, ref_nodes),
        check_edge_distribution(cand_edges, ref_edges),
        check_call_depth(cand_nodes, cand_edges, ref_nodes, ref_edges),
        check_tool_coverage(cand_nodes, ref_nodes),
        check_delegation_topology(cand_nodes, cand_edges, ref_nodes, ref_edges),
        check_element_diff(cand_nodes, cand_edges, ref_nodes, ref_edges),
    ]

    structural_checks = [c for c in checks if c["name"] != "element_level_diff"]
    all_passed = all(c["passed"] for c in (checks if strict else structural_checks))

    summary = {
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c["passed"]),
        "failed": sum(1 for c in checks if not c["passed"]),
    }
    ref_agents = _agent_ids(ref_nodes)
    cand_agents = _agent_ids(cand_nodes)

    return KGCompareResult(
        passed=all_passed,
        checks=checks,
        summary=summary,
        reference_stats={
            "nodes": len(ref_nodes),
            "edges": len(ref_edges),
            "agents": sorted(ref_agents),
        },
        candidate_stats={
            "nodes": len(cand_nodes),
            "edges": len(cand_edges),
            "agents": sorted(cand_agents),
        },
    )
