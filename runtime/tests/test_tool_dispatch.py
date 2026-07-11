#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine tool dispatch — delegation contract routing."""

import pytest

from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator
from mas.runtime.engine.manifest_tool_provider import build_manifest_tool_provider
from mas.runtime.engine.tool_dispatch import ToolExecutionError, execute_engine_tool


def test_execute_engine_tool_routes_delegate_tools():
    delegator = LlmDelegator(run_turn=lambda aid, task, cid, ccid: f"delegated:{aid}:{task}")
    out = execute_engine_tool(
        "delegate_to_db",
        delegation=delegator,
        arguments={"task": "check connections"},
    )
    assert out == "delegated:db:check connections"


def test_execute_engine_tool_forwards_caller_call_id_to_delegation():
    """caller_call_id (this TOOL_CALL's own resolved call_id, attached by
    the driver) must reach the DelegationContract unchanged, so a
    delegate's own execution_start.parent_call_id is a real native value."""
    seen: list[str] = []
    delegator = LlmDelegator(
        run_turn=lambda aid, task, cid, ccid: seen.append(ccid) or f"delegated:{aid}"
    )
    execute_engine_tool(
        "delegate_to_db",
        delegation=delegator,
        arguments={"task": "check connections"},
        caller_call_id="tool-call-xyz",
    )
    assert seen == ["tool-call-xyz"]


def test_execute_engine_tool_uses_manifest_provider(tmp_path):
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    (tool_dir / "calc.py").write_text(
        """
class CalcTool:
    def on_collect_tools(self, **_):
        return [{"name": "calculator", "description": "calc", "parameters": {"type": "object", "properties": {}}}]
    def on_execute_tool(self, name, args, **_):
        if name != "calculator":
            return None
        return {"result": 65536}
""",
        encoding="utf-8",
    )
    import yaml

    (tool_dir / "calculator.tool.yaml").write_text(
        yaml.safe_dump(
            {
                "kind": "Tool",
                "metadata": {"name": "calculator"},
                "spec": {
                    "description": "calc",
                    "impl": {"module_path": "./calc.py", "class_name": "CalcTool"},
                },
            }
        ),
        encoding="utf-8",
    )
    provider = build_manifest_tool_provider(
        [{"ref": "tools/calculator.tool.yaml"}],
        tmp_path,
    )
    out = execute_engine_tool(
        "calculator",
        arguments={"expression": "2**16"},
        tool_provider=provider,
    )
    assert "65536" in out


def test_unknown_tool_raises(tmp_path):
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    (tool_dir / "calc.py").write_text(
        """
class CalcTool:
    def on_collect_tools(self, **_):
        return [{"name": "calculator", "description": "calc", "parameters": {"type": "object", "properties": {}}}]
    def on_execute_tool(self, name, args, **_):
        if name != "calculator":
            return None
        return {"ok": True}
""",
        encoding="utf-8",
    )
    import yaml

    (tool_dir / "calculator.tool.yaml").write_text(
        yaml.safe_dump(
            {
                "kind": "Tool",
                "metadata": {"name": "calculator"},
                "spec": {"impl": {"module_path": "./calc.py", "class_name": "CalcTool"}},
            }
        ),
        encoding="utf-8",
    )
    provider = build_manifest_tool_provider(
        [{"ref": "tools/calculator.tool.yaml"}],
        tmp_path,
    )
    with pytest.raises(ToolExecutionError, match="not found"):
        execute_engine_tool("missing", tool_provider=provider)
