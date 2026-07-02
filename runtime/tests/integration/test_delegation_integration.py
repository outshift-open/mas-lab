#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation manifest → OpenAI tool schema integration."""

from mas.runtime.boundary.delegation import (
    delegation_targets,
    openai_delegation_tools,
    parse_delegate_tool_name,
    uses_llm_peer_delegation,
    workflow_type,
)


def test_delegation_targets_from_workflow_topology():
    manifest = {
        "metadata": {"name": "moderator"},
        "spec": {
            "workflow": {
                "entry": "moderator",
                "nodes": [
                    {"id": "moderator", "delegates_to": ["planner", "reviewer"]},
                    {"id": "planner", "delegates_to": ["reviewer"]},
                ],
            },
        },
    }
    assert delegation_targets(manifest, agent_id="moderator") == ["planner", "reviewer"]


def test_delegation_without_collaboration_block():
    manifest = {
        "metadata": {"name": "entry"},
        "spec": {
            "workflow": {
                "entry": "entry",
                "nodes": [
                    {
                        "id": "entry",
                        "delegates_to": ["alpha", "beta", "gamma"],
                    },
                ],
            }
        },
    }
    assert delegation_targets(manifest, agent_id="entry") == ["alpha", "beta", "gamma"]
    tools = openai_delegation_tools(manifest, agent_id="entry")
    assert [t["function"]["name"] for t in tools] == [
        "delegate_to_alpha",
        "delegate_to_beta",
        "delegate_to_gamma",
    ]


def test_collaboration_none_allows_delegation_tools():
    manifest = {
        "metadata": {"name": "entry"},
        "spec": {
            "collaboration": {"type": "none"},
            "workflow": {
                "entry": "entry",
                "nodes": [{"id": "entry", "delegates_to": ["alpha"]}],
            },
        },
    }
    assert delegation_targets(manifest, agent_id="entry") == ["alpha"]


def test_sequential_workflow_suppresses_delegate_tools():
    manifest = {
        "metadata": {"name": "schedule_agent"},
        "spec": {
            "workflow": {
                "type": "sequential",
                "entry": "schedule_agent",
                "nodes": [{"id": "schedule_agent", "delegates_to": ["itinerary_agent"]}],
            },
        },
    }
    assert workflow_type(manifest) == "sequential"
    assert not uses_llm_peer_delegation(manifest)
    assert delegation_targets(manifest, agent_id="schedule_agent") == []


def test_single_workflow_suppresses_delegate_tools():
    manifest = {
        "metadata": {"name": "generalist"},
        "spec": {"workflow": {"type": "single", "entry": "generalist", "nodes": [{"id": "generalist"}]}},
    }
    assert not uses_llm_peer_delegation(manifest)
    assert delegation_targets(manifest) == []


def test_openai_delegation_tools_shape():
    manifest = {
        "spec": {
            "workflow": {"nodes": [{"delegates_to": ["worker"]}]},
        }
    }
    tools = openai_delegation_tools(manifest)
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "delegate_to_worker"
    assert "task" in tools[0]["function"]["parameters"]["properties"]


def test_delegation_targets_unknown_agent_id_returns_empty():
    manifest = {
        "spec": {
            "workflow": {
                "nodes": [
                    {"id": "entry", "delegates_to": ["alpha"]},
                    {"id": "other", "delegates_to": ["beta"]},
                ],
            },
        },
    }
    assert delegation_targets(manifest, agent_id="missing") == []


def test_delegation_targets_empty_delegates_on_matched_node():
    manifest = {
        "metadata": {"name": "leaf"},
        "spec": {
            "workflow": {
                "entry": "leaf",
                "nodes": [
                    {"id": "leaf", "delegates_to": []},
                    {"id": "other", "delegates_to": ["worker"]},
                ],
            },
        },
    }
    assert delegation_targets(manifest, agent_id="leaf") == []


def test_parse_delegate_tool_name():
    assert parse_delegate_tool_name("delegate_to_telemetry") == "telemetry"
    assert parse_delegate_tool_name("delegate_to_") is None
    assert parse_delegate_tool_name("calculator") is None
