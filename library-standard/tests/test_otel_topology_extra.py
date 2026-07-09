#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Extra coverage for topology branches not hit by test_otel_topology.py:
string-form agent ids, execution-event agent discovery, conditional
dynamism, and every derive_app_name resolution path."""

from __future__ import annotations

from mas.library.standard.lib.observability.otel.topology import (
    build_topology,
    derive_app_name,
    determinism_score,
    graph_span_attributes,
    topology_dynamism,
)


def test_build_topology_string_agent_ids_and_execution_agents() -> None:
    events = [
        {"kind": "system_specification", "agent_ids": ["planner", "worker"]},
        {"kind": "execution_start", "agent_id": "solo"},
        {"kind": "mas_call_start", "agent_id": "caller"},
    ]
    topo = build_topology(events)
    assert {n["id"] for n in topo["nodes"]} == {"planner", "worker", "solo", "caller"}
    assert topo["edges"] == []


def test_build_topology_selected_agent_and_conditional_routing() -> None:
    events = [
        {"kind": "routing", "source_agent_id": "a", "selected_agent": "b"},
    ]
    topo = build_topology(events)
    edge = topo["edges"][0]
    assert edge == {"source": "a", "target": "b", "kind": "routing", "conditional": True}
    assert topology_dynamism(topo) == "dynamic"
    assert determinism_score(topo) == 0.0


def test_build_topology_agent_dict_name_fallback() -> None:
    events = [{"kind": "system_specification", "agents": [{"name": "named"}]}]
    topo = build_topology(events)
    assert {n["id"] for n in topo["nodes"]} == {"named"}


def test_graph_span_attributes_custom_protocol() -> None:
    topo = {"nodes": [{"id": "a", "name": "a"}], "edges": []}
    attrs = graph_span_attributes(topo, protocol="A2A")
    assert attrs["gen_ai.ioa.graph.protocol"] == "A2A"


def test_derive_app_name_top_level_key() -> None:
    assert derive_app_name([{"app_name": "top"}]) == "top"
    assert derive_app_name([{"application_id": "appid"}]) == "appid"


def test_derive_app_name_system_specification_name() -> None:
    events = [{"kind": "system_specification", "name": "spec-app"}]
    assert derive_app_name(events) == "spec-app"


def test_derive_app_name_fallback_when_absent() -> None:
    assert derive_app_name([{"kind": "noise"}], fallback="fb") == "fb"
    assert derive_app_name([]) == ""
