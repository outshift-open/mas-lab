#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation manifest → OpenAI tool schema integration."""

from mas.runtime.boundary.delegation import delegation_targets, openai_delegation_tools


def test_delegation_targets_from_workflow_nodes():
    manifest = {
        "spec": {
            "collaboration": {"mode": "hierarchical"},
            "workflow": {
                "nodes": [
                    {"id": "moderator", "delegates_to": ["planner", "reviewer"]},
                    {"id": "planner", "delegates_to": ["reviewer"]},
                ]
            },
        }
    }
    assert delegation_targets(manifest) == ["planner", "reviewer"]


def test_delegation_disabled_when_collaboration_none():
    manifest = {"spec": {"collaboration": {"mode": "none"}, "workflow": {"nodes": []}}}
    assert delegation_targets(manifest) == []


def test_openai_delegation_tools_shape():
    manifest = {
        "spec": {
            "collaboration": {"mode": "peer"},
            "workflow": {"nodes": [{"delegates_to": ["worker"]}]},
        }
    }
    tools = openai_delegation_tools(manifest)
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "delegate_to_worker"
    assert "task" in tools[0]["function"]["parameters"]["properties"]
