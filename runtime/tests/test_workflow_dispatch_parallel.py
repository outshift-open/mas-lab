#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""workflow.nodes[].dispatch: parallel is parsed as a first-class fan-out flag."""

from mas.runtime.boundary.delegation.policy import node_dispatch, uses_parallel_dispatch


def test_node_dispatch_reads_parallel_flag():
    manifest = {
        "spec": {
            "behavior": {"delegation_style": "typed"},
            "workflow": {
                "entry": "moderator",
                "nodes": [
                    {
                        "id": "moderator",
                        "delegates_to": ["schedule_agent", "concierge_agent"],
                        "dispatch": "parallel",
                    }
                ],
            },
        }
    }
    assert node_dispatch(manifest, agent_id="moderator") == "parallel"
    assert uses_parallel_dispatch(manifest, agent_id="moderator")
    assert not uses_parallel_dispatch(manifest, agent_id="schedule_agent")
