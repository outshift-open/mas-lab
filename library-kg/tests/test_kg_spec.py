#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas.library.kg.core.spec — build_spec_nodes, merge_spec_into_kg."""

from mas.library.kg.core.spec import build_spec_nodes, merge_spec_into_kg

SIMPLE_SPEC = {
    "version": "v1",
    "intent": "Classify patient urgency.",
    "agents": [
        {
            "id": "cra",
            "role": "clinical_reasoner",
            "capabilities": ["esi_assessment"],
            "skills": ["triage_rule"],
            "tools": ["retrieve_esi_handbook"],
        },
        {
            "id": "paa",
            "role": "priority_assigner",
            "capabilities": ["priority_assignment"],
            "skills": [],
            "tools": [],
        },
    ],
    "tools": [
        {
            "id": "retrieve_esi_handbook",
            "description": "Look up ESI chunks.",
            "in_schema": {"query": "str"},
            "out_schema": {"chunks": "list"},
        }
    ],
    "skills": [
        {
            "id": "triage_rule",
            "description": "Map vitals to ESI.",
            "requires": ["vitals"],
            "concludes": "esi_level",
        }
    ],
}


# ---------------------------------------------------------------------------
# build_spec_nodes
# ---------------------------------------------------------------------------


class TestBuildSpecNodes:
    def test_node_types_present(self):
        nodes, edges = build_spec_nodes(SIMPLE_SPEC)
        types = {n["node_type"] for n in nodes}
        assert "IntentSpec" in types
        assert "AgentSpec" in types
        assert "ToolSpec" in types
        assert "SkillSpec" in types

    def test_node_counts(self):
        nodes, _ = build_spec_nodes(SIMPLE_SPEC)
        from collections import Counter

        counts = Counter(n["node_type"] for n in nodes)
        assert counts["IntentSpec"] == 1
        assert counts["AgentSpec"] == 2
        assert counts["ToolSpec"] == 1
        assert counts["SkillSpec"] == 1

    def test_stable_ids(self):
        nodes1, _ = build_spec_nodes(SIMPLE_SPEC)
        nodes2, _ = build_spec_nodes(SIMPLE_SPEC)
        ids1 = {n["id"] for n in nodes1}
        ids2 = {n["id"] for n in nodes2}
        assert ids1 == ids2

    def test_ids_use_spec_prefix(self):
        nodes, _ = build_spec_nodes(SIMPLE_SPEC)
        for n in nodes:
            assert n["id"].startswith("spec:")

    def test_declared_edges(self):
        _, edges = build_spec_nodes(SIMPLE_SPEC)
        edge_types = {e["edge_type"] for e in edges}
        assert "declaresSkill" in edge_types
        assert "mayInvoke" in edge_types

    def test_text_field_present(self):
        nodes, _ = build_spec_nodes(SIMPLE_SPEC)
        for n in nodes:
            assert "_text" in n
            assert n["_text"]  # non-empty

    def test_version_propagated(self):
        nodes, _ = build_spec_nodes(SIMPLE_SPEC)
        for n in nodes:
            assert n["version"] == "v1"

    def test_no_intent_ok(self):
        spec = {"agents": [{"id": "a", "skills": [], "tools": []}]}
        nodes, _ = build_spec_nodes(spec)
        types = [n["node_type"] for n in nodes]
        assert "IntentSpec" not in types

    def test_empty_spec(self):
        nodes, edges = build_spec_nodes({})
        assert nodes == []
        assert edges == []


# ---------------------------------------------------------------------------
# merge_spec_into_kg
# ---------------------------------------------------------------------------


class TestMergeSpecIntoKG:
    def test_spec_nodes_added(self):
        kg = {"nodes": [], "edges": []}
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        types = {n["node_type"] for n in kg["nodes"]}
        assert "AgentSpec" in types
        assert "ToolSpec" in types

    def test_no_duplicate_nodes(self):
        kg = {"nodes": [], "edges": []}
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        first_count = len(kg["nodes"])
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        assert len(kg["nodes"]) == first_count  # idempotent

    def test_conformance_edges_agent_call(self):
        kg = {
            "nodes": [
                {"id": "call-1", "node_type": "AgentCall", "agentId": "cra"},
            ],
            "edges": [],
        }
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        edge_types = {e["edge_type"] for e in kg["edges"]}
        assert "instanceOf" in edge_types

    def test_conformance_edges_tool_call(self):
        kg = {
            "nodes": [
                {"id": "tc-1", "node_type": "ToolCall", "toolName": "retrieve_esi_handbook"},
            ],
            "edges": [],
        }
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        edge_types = {e["edge_type"] for e in kg["edges"]}
        assert "invokes" in edge_types

    def test_no_conformance_for_unknown_agent(self):
        kg = {
            "nodes": [
                {"id": "call-x", "node_type": "AgentCall", "agentId": "unknown_agent"},
            ],
            "edges": [],
        }
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        instance_edges = [e for e in kg["edges"] if e.get("edge_type") == "instanceOf"]
        assert len(instance_edges) == 0

    def test_metadata_updated(self):
        kg = {"nodes": [], "edges": []}
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        assert kg["metadata"]["spec_injected"] is True
        assert kg["metadata"]["spec_node_count"] > 0

    def test_existing_nodes_preserved(self):
        kg = {
            "nodes": [{"id": "runtime-node", "node_type": "AgentCall", "agentId": "cra"}],
            "edges": [],
        }
        merge_spec_into_kg(kg, SIMPLE_SPEC)
        runtime_nodes = [n for n in kg["nodes"] if n["id"] == "runtime-node"]
        assert len(runtime_nodes) == 1
