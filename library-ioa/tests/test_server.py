#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from library_ioa.plugins.mcp.server import MCPToolServerFactory, _python_type_for_schema


def _write_tool(tmp_path: Path, *, extra_spec: str = "", class_body: str | None = None) -> Path:
    tool_module = tmp_path / "sample_tool.py"
    tool_module.write_text(
        class_body
        or (
            "class SampleTool:\n"
            "    def execute(self, **kwargs):\n"
            "        return {'answer': kwargs['a'] + kwargs['b']}\n"
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "sample.tool.yaml"
    manifest_path.write_text(
        "apiVersion: mas/v1\n"
        "kind: Tool\n"
        "metadata:\n"
        "  name: sample-tool\n"
        "  description: Catalogue label\n"
        "spec:\n"
        "  description: Adds two integers\n"
        "  parameters:\n"
        "    - name: a\n"
        "      type: integer\n"
        "      required: true\n"
        "    - name: b\n"
        "      type: integer\n"
        "      required: true\n"
        "  returns:\n"
        "    type: integer\n"
        "  idempotent: true\n"
        f"{extra_spec}"
        "  impl:\n"
        "    kind: python\n"
        f"    module_path: {tool_module.name}\n"
        "    class_name: SampleTool\n",
        encoding="utf-8",
    )
    return manifest_path


def test_factory_wraps_manifest_tool(tmp_path: Path) -> None:
    factory = MCPToolServerFactory.from_manifest(_write_tool(tmp_path))
    assert len(factory._tools) == 1
    assert factory._tools[0]["name"] == "sample-tool"
    assert factory._tools[0]["description"] == "Adds two integers"
    assert factory._tools[0]["mcp"]["title"] == "Catalogue label"
    assert factory._tools[0]["mcp"]["annotations"]["idempotentHint"] is True
    assert factory._tools[0]["mcp"]["outputSchema"]["type"] == "integer"
    assert factory._tools[0]["fn"](a=2, b=3) == {"answer": 5}


def test_factory_prefers_call_tool_over_execute(tmp_path: Path) -> None:
    factory = MCPToolServerFactory.from_manifest(
        _write_tool(
            tmp_path,
            class_body=(
                "class SampleTool:\n"
                "    def execute(self, **kwargs):\n"
                "        raise AssertionError('execute must not be used when call_tool exists')\n"
                "    def call_tool(self, tool_name, arguments):\n"
                "        return {'tool': tool_name, 'sum': arguments['a'] + arguments['b']}\n"
            ),
        )
    )
    assert factory._tools[0]["fn"](a=2, b=3) == {"tool": "sample-tool", "sum": 5}


def test_factory_optional_parameter_and_unknown_type() -> None:
    assert _python_type_for_schema("integer") is int
    assert _python_type_for_schema("unknown") is not int


def test_from_manifest_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        MCPToolServerFactory.from_manifest(bad)

    missing_name = tmp_path / "noname.tool.yaml"
    missing_name.write_text(
        "apiVersion: mas/v1\nkind: Tool\nmetadata: {}\nspec:\n  impl:\n    module_path: x.py\n    class_name: X\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata.name"):
        MCPToolServerFactory.from_manifest(missing_name)

    no_impl = tmp_path / "noimpl.tool.yaml"
    no_impl.write_text(
        "apiVersion: mas/v1\nkind: Tool\nmetadata:\n  name: t\nspec: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="module_path"):
        MCPToolServerFactory.from_manifest(no_impl)

    no_module = tmp_path / "nomod.tool.yaml"
    no_module.write_text(
        "apiVersion: mas/v1\nkind: Tool\nmetadata:\n  name: t\n"
        "spec:\n  impl:\n    module_path: missing.py\n    class_name: X\n",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError):
        MCPToolServerFactory.from_manifest(no_module)


def test_from_manifest_missing_class_name(tmp_path: Path) -> None:
    module = tmp_path / "tool.py"
    module.write_text("class SampleTool:\n    def execute(self, **kwargs):\n        return kwargs\n")
    manifest = tmp_path / "t.tool.yaml"
    manifest.write_text(
        "apiVersion: mas/v1\nkind: Tool\nmetadata:\n  name: t\nspec:\n  impl:\n    module_path: tool.py\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="class_name"):
        MCPToolServerFactory.from_manifest(manifest)


def test_run_stdio_and_http_and_rejects_unknown() -> None:
    factory = MCPToolServerFactory(server_name="demo")
    factory._server = MagicMock()
    factory.run(transport="stdio")
    factory._server.run.assert_called_with(transport="stdio")
    factory.run(transport="streamable-http", host="127.0.0.1", port=9001)
    factory._server.run.assert_called_with(transport="streamable-http", host="127.0.0.1", port=9001)
    factory.run(transport="sse", host="127.0.0.1", port=9001)
    factory._server.run.assert_called_with(transport="sse", host="127.0.0.1", port=9001)
    with pytest.raises(ValueError, match="Unsupported MCP transport"):
        factory.run(transport="grpc")
