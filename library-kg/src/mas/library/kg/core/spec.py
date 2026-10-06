#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Spec → KG: inject a MAS application spec as a shared, embed-once sub-graph.

The spec is design-time, run-independent procedural memory (agent intent,
skills, capabilities; tool descriptions + parameter/return schemas).  It is
interned once per app-version and shared across all run KGs; runtime nodes
link into it via conformance edges.  This gives every run an external
reference (P*) to measure adherence against.

Pure stdlib — no external dependencies.

Public API
----------
build_spec_nodes(mas_spec) → (nodes, edges)
merge_spec_into_kg(kg_doc, mas_spec) → kg_doc
"""

from __future__ import annotations

import hashlib
from typing import Any

__all__ = ["build_spec_nodes", "merge_spec_into_kg"]


def _sid(kind: str, key: str) -> str:
    return f"spec:{kind}:{key}"


def _content_hash(obj: Any) -> str:
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:12]


def build_spec_nodes(
    mas_spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(nodes, edges)`` for the shared spec sub-graph from *mas_spec*.

    Node types: ``IntentSpec`` (MAS goal), ``AgentSpec``, ``ToolSpec``, ``SkillSpec``.
    Stable ids (``spec:agent:<id>`` …) so the sub-graph is shared across runs and
    can be embedded once.  ``_text`` carries the description to embed for semantic
    edges.

    Args:
        mas_spec: Application spec dict with optional keys:
            ``version``, ``intent`` / ``goal``, ``agents``, ``tools``, ``skills``.

    Returns:
        Tuple ``(nodes, edges)`` — both lists use standard KG dict format.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    version = str(mas_spec.get("version") or _content_hash(mas_spec))

    intent = mas_spec.get("intent") or mas_spec.get("goal")
    if intent:
        iid = _sid("intent", "mas")
        nodes.append(
            {
                "id": iid,
                "node_type": "IntentSpec",
                "version": version,
                "content": str(intent),
                "_text": str(intent),
            }
        )

    for sk in mas_spec.get("skills") or []:
        sid = _sid("skill", str(sk.get("id")))
        nodes.append(
            {
                "id": sid,
                "node_type": "SkillSpec",
                "version": version,
                "requires": list(sk.get("requires") or []),
                "concludes": sk.get("concludes"),
                "content": str(sk.get("description") or sk.get("id")),
                "_text": str(sk.get("description") or sk.get("id")),
            }
        )

    for t in mas_spec.get("tools") or []:
        tid = _sid("tool", str(t.get("id")))
        nodes.append(
            {
                "id": tid,
                "node_type": "ToolSpec",
                "version": version,
                "in_schema": t.get("in_schema") or {},
                "out_schema": t.get("out_schema") or {},
                "content": str(t.get("description") or t.get("id")),
                "_text": str(t.get("description") or t.get("id")),
            }
        )

    for a in mas_spec.get("agents") or []:
        aid = _sid("agent", str(a.get("id")))
        desc = a.get("intent") or a.get("role") or a.get("description") or a.get("id")
        nodes.append(
            {
                "id": aid,
                "node_type": "AgentSpec",
                "version": version,
                "role": a.get("role"),
                "intent": a.get("intent"),
                "capabilities": list(a.get("capabilities") or []),
                "skills": list(a.get("skills") or []),
                "content": str(desc),
                "_text": str(desc),
            }
        )
        for sk in a.get("skills") or []:
            edges.append(
                {
                    "from_id": aid,
                    "to_id": _sid("skill", str(sk)),
                    "edge_type": "declaresSkill",
                }
            )
        for tl in a.get("tools") or []:
            edges.append(
                {
                    "from_id": aid,
                    "to_id": _sid("tool", str(tl)),
                    "edge_type": "mayInvoke",
                }
            )

    return nodes, edges


def merge_spec_into_kg(
    kg_doc: dict[str, Any],
    mas_spec: dict[str, Any],
) -> dict[str, Any]:
    """Add shared spec nodes + conformance edges (runtime → spec) into a KG doc.

    Spec nodes are interned by id — already-present nodes are not duplicated.
    Conformance edges are created for:
    - ``AgentCall`` / ``LLMCall`` → ``AgentSpec`` via ``instanceOf``
    - ``ToolCall`` → ``ToolSpec`` via ``invokes``

    Args:
        kg_doc:  KG document dict (modified in place).
        mas_spec: Application spec dict (see :func:`build_spec_nodes`).

    Returns:
        The same ``kg_doc`` dict with spec nodes and conformance edges added.
    """
    spec_nodes, spec_edges = build_spec_nodes(mas_spec)

    kg_nodes = kg_doc.setdefault("nodes", [])
    kg_edges = kg_doc.setdefault("edges", [])

    existing_ids = {n.get("id") for n in kg_nodes}
    for n in spec_nodes:
        if n["id"] not in existing_ids:
            kg_nodes.append(n)

    # Build spec lookups: agent/tool short id → spec node id
    spec_agent = {
        n["id"].split(":")[-1]: n["id"] for n in spec_nodes if n["node_type"] == "AgentSpec"
    }
    spec_tool = {
        n["id"].split(":")[-1]: n["id"] for n in spec_nodes if n["node_type"] == "ToolSpec"
    }

    # Add conformance edges: runtime call → spec
    for n in kg_nodes:
        nt = n.get("node_type", "")
        aid = str(n.get("agentId") or n.get("agent_id") or "")
        if nt in ("AgentCall", "LLMCall") and aid in spec_agent:
            kg_edges.append(
                {
                    "from_id": n["id"],
                    "to_id": spec_agent[aid],
                    "edge_type": "instanceOf",
                }
            )
        tid = str(
            n.get("toolId") or n.get("tool_id") or n.get("toolName") or n.get("tool_name") or ""
        )
        if nt == "ToolCall" and tid in spec_tool:
            kg_edges.append(
                {
                    "from_id": n["id"],
                    "to_id": spec_tool[tid],
                    "edge_type": "invokes",
                }
            )

    metadata = kg_doc.setdefault("metadata", {})
    metadata["spec_injected"] = True
    metadata["spec_node_count"] = len(spec_nodes)
    return kg_doc
