#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

from mas.library.standard.lib.observability.otel.topology import (
    build_topology,
    determinism_score,
    derive_app_name,
    graph_span_attributes,
    has_topology,
    topology_dynamism,
)


def test_build_topology_nodes_edges_and_kinds() -> None:
    events = [
        {"kind": "system_specification", "agents": [{"id": "planner"}, {"id": "worker"}]},
        {"kind": "routing", "source_agent_id": "planner", "target_agent_id": "worker"},
        {"kind": "agent_communication", "source_agent_id": "worker", "target_agent_id": "planner"},
    ]
    topo = build_topology(events)
    assert {n["id"] for n in topo["nodes"]} == {"planner", "worker"}
    assert len(topo["edges"]) == 2
    assert {e["kind"] for e in topo["edges"]} == {"routing", "communication"}


def test_graph_span_attributes_and_scores() -> None:
    topo = {
        "nodes": [{"id": "a", "name": "a"}, {"id": "b", "name": "b"}],
        "edges": [
            {"source": "a", "target": "b", "conditional": False},
            {"source": "b", "target": "a", "conditional": True},
        ],
    }
    attrs = graph_span_attributes(topo)
    assert attrs["ioa_observe.span.kind"] == "graph"
    assert json.loads(attrs["gen_ai.ioa.graph"]) == topo
    assert attrs["gen_ai.ioa.graph_dynamism"] == "dynamic"
    assert attrs["gen_ai.ioa.graph_determinism_score"] == 0.5


def test_topology_helpers_static_empty_and_app_name_derivation() -> None:
    static_topo = {"nodes": [{"id": "a", "name": "a"}], "edges": []}
    assert topology_dynamism(static_topo) == "static"
    assert determinism_score(static_topo) == 1.0
    assert has_topology(static_topo)

    events = [
        {"kind": "execution_start", "metadata": {"app_name": "sample-app"}},
    ]
    assert derive_app_name(events, fallback="fallback") == "sample-app"
