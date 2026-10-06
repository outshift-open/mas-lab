#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas.library.kg.core.query — KGIndex, FacetQuery, KGSource, KGView."""

import json

import pytest

from mas.library.kg.core.query import FacetQuery, KGIndex, KGSource, KGView

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_kg():
    return {
        "run_id": "r1",
        "nodes": [
            {
                "id": "sess-1",
                "node_type": "Session",
                "sessionId": "sess-1",
                "startTime": 0.0,
                "endTime": 5.0,
            },
            {
                "id": "agent-call-1",
                "node_type": "AgentCall",
                "agentId": "orchestrator",
                "sessionId": "sess-1",
                "runId": "r1",
                "startTime": 1.0,
                "endTime": 4.0,
            },
            {
                "id": "agent-call-2",
                "node_type": "AgentCall",
                "agentId": "analyst",
                "sessionId": "sess-1",
                "runId": "r1",
                "startTime": 1.5,
                "endTime": 3.0,
                "parentCallId": "agent-call-1",
            },
            {
                "id": "llm-1",
                "node_type": "LLMCall",
                "agentId": "orchestrator",
                "sessionId": "sess-1",
                "startTime": 1.1,
                "endTime": 1.9,
            },
            {
                "id": "tool-1",
                "node_type": "ToolCall",
                "agentId": "analyst",
                "toolName": "search",
                "sessionId": "sess-1",
                "startTime": 2.0,
                "endTime": 2.5,
            },
            {"id": "state-1", "node_type": "State", "sessionId": "sess-1", "startTime": 0.5},
        ],
        "edges": [
            {"from_id": "agent-call-1", "to_id": "agent-call-2", "edge_type": "contains"},
            {"from_id": "agent-call-1", "to_id": "llm-1", "edge_type": "contains"},
            {"from_id": "agent-call-2", "to_id": "tool-1", "edge_type": "contains"},
        ],
    }


# ---------------------------------------------------------------------------
# KGIndex tests
# ---------------------------------------------------------------------------


class TestKGIndex:
    def test_from_doc(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        assert idx.session is not None
        assert idx.session["id"] == "sess-1"

    def test_typed_accessors(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        assert len(idx.agent_calls) == 2
        assert len(idx.llm_calls) == 1
        assert len(idx.tool_calls) == 1

    def test_calls_by_time_sorted(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        calls = idx.calls_by_time
        starts = [c["startTime"] for c in calls]
        assert starts == sorted(starts)

    def test_node_lookup(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        n = idx.node("llm-1")
        assert n is not None
        assert n["node_type"] == "LLMCall"
        assert idx.node("nonexistent") is None

    def test_out_neighbors(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        children = idx.out_neighbors("agent-call-1", edge_type="contains")
        child_ids = {c["id"] for c in children}
        assert child_ids == {"agent-call-2", "llm-1"}

    def test_out_neighbors_no_filter(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        children = idx.out_neighbors("agent-call-1")
        assert len(children) == 2

    def test_in_neighbors(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        parents = idx.in_neighbors("agent-call-2", edge_type="contains")
        assert len(parents) == 1
        assert parents[0]["id"] == "agent-call-1"

    def test_nodes_of_type(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        states = idx.nodes_of_type("State")
        assert len(states) == 1

    def test_find_root_agent_call_auto(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        root = idx.find_root_agent_call()
        assert root is not None
        assert root["id"] == "agent-call-1"

    def test_find_root_agent_call_by_agent_id(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        root = idx.find_root_agent_call("analyst")
        assert root is not None
        assert root["agentId"] == "analyst"

    def test_find_root_agent_call_unknown_agent(self, simple_kg):
        idx = KGIndex.from_doc(simple_kg)
        root = idx.find_root_agent_call("nonexistent")
        # Falls back to auto-detect
        assert root is not None

    def test_empty_kg(self):
        idx = KGIndex.from_doc({"nodes": [], "edges": []})
        assert idx.session is None
        assert idx.agent_calls == []
        assert idx.find_root_agent_call() is None

    def test_edge_format_variants(self):
        """Supports source/target as well as from_id/to_id edge keys."""
        kg = {
            "nodes": [
                {"id": "a", "node_type": "AgentCall"},
                {"id": "b", "node_type": "LLMCall"},
            ],
            "edges": [{"source": "a", "target": "b", "edge_type": "contains"}],
        }
        idx = KGIndex.from_doc(kg)
        children = idx.out_neighbors("a")
        assert len(children) == 1
        assert children[0]["id"] == "b"


# ---------------------------------------------------------------------------
# FacetQuery tests
# ---------------------------------------------------------------------------


class TestFacetQuery:
    def test_default_all_none(self):
        q = FacetQuery()
        assert q.session_id is None
        assert q.agent_ids is None

    def test_to_dict_omits_none(self):
        q = FacetQuery(session_id="s1")
        d = q.to_dict()
        assert "session_id" in d
        assert "agent_ids" not in d

    def test_from_dict_snake_case(self):
        q = FacetQuery.from_dict({"session_id": "s1", "agent_ids": ["a", "b"]})
        assert q.session_id == "s1"
        assert q.agent_ids == ["a", "b"]

    def test_from_dict_camel_case(self):
        q = FacetQuery.from_dict({"sessionId": "s2", "callTypes": ["LLMCall"]})
        assert q.session_id == "s2"
        assert q.call_types == ["LLMCall"]

    def test_from_dict_time_range(self):
        q = FacetQuery.from_dict({"timeRange": [1.0, 5.0]})
        assert q.time_range == (1.0, 5.0)

    def test_roundtrip_serialisation(self):
        q = FacetQuery(
            session_id="s1",
            agent_ids=["a"],
            node_types=["State"],
            time_range=(0.0, 10.0),
        )
        q2 = FacetQuery.from_dict(q.to_dict())
        assert q2.session_id == q.session_id
        assert q2.agent_ids == q.agent_ids
        assert q2.node_types == q.node_types
        assert q2.time_range == q.time_range


# ---------------------------------------------------------------------------
# KGSource tests
# ---------------------------------------------------------------------------


class TestKGSource:
    def test_subgraph_no_query_returns_full(self, simple_kg):
        src = KGSource(simple_kg)
        sub = src.subgraph()
        assert len(sub["nodes"]) == len(simple_kg["nodes"])
        assert len(sub["edges"]) == len(simple_kg["edges"])

    def test_subgraph_node_types_filter(self, simple_kg):
        src = KGSource(simple_kg)
        sub = src.subgraph(FacetQuery(node_types=["AgentCall"]))
        assert all(n["node_type"] == "AgentCall" for n in sub["nodes"])
        assert len(sub["nodes"]) == 2

    def test_subgraph_call_types_alias(self, simple_kg):
        src = KGSource(simple_kg)
        sub = src.subgraph(FacetQuery(call_types=["LLMCall"]))
        assert all(n["node_type"] == "LLMCall" for n in sub["nodes"])

    def test_subgraph_agent_ids_filter(self, simple_kg):
        src = KGSource(simple_kg)
        sub = src.subgraph(
            FacetQuery(agent_ids=["orchestrator"], node_types=["AgentCall", "LLMCall"])
        )
        for n in sub["nodes"]:
            if n["node_type"] in ("AgentCall", "LLMCall"):
                assert n.get("agentId", "").lower() == "orchestrator"

    def test_subgraph_drops_dangling_edges(self, simple_kg):
        src = KGSource(simple_kg)
        # Filter to only AgentCall nodes — edges that reference LLMCall/ToolCall should be dropped
        sub = src.subgraph(FacetQuery(node_types=["AgentCall"]))
        kept_ids = {n["id"] for n in sub["nodes"]}
        for e in sub["edges"]:
            from_id = e.get("from_id") or e.get("source") or ""
            to_id = e.get("to_id") or e.get("target") or ""
            assert from_id in kept_ids
            assert to_id in kept_ids

    def test_subgraph_time_range(self, simple_kg):
        src = KGSource(simple_kg)
        sub = src.subgraph(FacetQuery(time_range=(1.0, 2.0)))
        for n in sub["nodes"]:
            start = float(n.get("startTime") or 0)
            end = float(n.get("endTime") or n.get("startTime") or 0)
            assert end >= 1.0 and start <= 2.0

    def test_subgraph_edge_types_filter(self, simple_kg):
        src = KGSource(simple_kg)
        sub = src.subgraph(FacetQuery(edge_types=["contains"]))
        assert all(e.get("edge_type") == "contains" for e in sub["edges"])

    def test_load_returns_nodes_edges(self, simple_kg):
        src = KGSource(simple_kg)
        nodes, edges = src.load()
        assert len(nodes) == len(simple_kg["nodes"])
        assert len(edges) == len(simple_kg["edges"])

    def test_from_file(self, simple_kg, tmp_path):
        p = tmp_path / "kg.jsonld"
        p.write_text(json.dumps(simple_kg))
        src = KGSource.from_file(p)
        sub = src.subgraph()
        assert len(sub["nodes"]) == len(simple_kg["nodes"])


# ---------------------------------------------------------------------------
# KGView tests
# ---------------------------------------------------------------------------


class TestKGView:
    def test_query_by_type(self, simple_kg):
        view = KGView.from_kg(simple_kg)
        llm = view.query("LLMCall")
        assert len(llm) == 1
        assert llm[0]["id"] == "llm-1"

    def test_query_with_filter(self, simple_kg):
        view = KGView.from_kg(simple_kg)
        root_agents = view.query("AgentCall", parentCallId=None)
        assert len(root_agents) == 1
        assert root_agents[0]["id"] == "agent-call-1"

    def test_query_case_insensitive_string(self, simple_kg):
        view = KGView.from_kg(simple_kg)
        results = view.query("AgentCall", agentId="ORCHESTRATOR")
        assert len(results) == 1

    def test_query_sorted_by_start_time(self, simple_kg):
        view = KGView.from_kg(simple_kg)
        agents = view.query("AgentCall")
        starts = [n.get("startTime") for n in agents]
        assert starts == sorted(starts)

    def test_get_by_id(self, simple_kg):
        view = KGView.from_kg(simple_kg)
        n = view.get("tool-1")
        assert n is not None
        assert n["node_type"] == "ToolCall"

    def test_get_missing_id(self, simple_kg):
        view = KGView.from_kg(simple_kg)
        assert view.get("nonexistent") is None
        assert view.get(None) is None

    def test_types(self, simple_kg):
        view = KGView.from_kg(simple_kg)
        types = view.types()
        assert "AgentCall" in types
        assert "LLMCall" in types

    def test_empty_kg(self):
        view = KGView.from_kg({"nodes": [], "edges": []})
        assert view.query("AgentCall") == []
        assert view.get("any") is None
