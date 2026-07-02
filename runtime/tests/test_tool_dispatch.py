#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine tool dispatch — delegation contract routing."""

from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator
from mas.runtime.engine.tool_dispatch import execute_engine_tool


def test_execute_engine_tool_routes_delegate_tools():
    delegator = LlmDelegator(run_turn=lambda aid, task: f"delegated:{aid}:{task}")
    out = execute_engine_tool(
        "delegate_to_db",
        delegation=delegator,
        arguments={"task": "check connections"},
    )
    assert out == "delegated:db:check connections"


def test_execute_engine_tool_falls_through_to_registered_tools():
    out = execute_engine_tool("calculator", arguments={"expression": "2**16"})
    assert "65536" in out
