#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from library_ioa.plugins.mcp.server import _build_parser, main


def test_parser_serve_and_tools_commands() -> None:
    parser = _build_parser()
    serve = parser.parse_args(
        [
            "serve",
            "--tool-manifest",
            "tool.yaml",
            "--transport",
            "streamable-http",
            "--host",
            "0.0.0.0",
            "--port",
            "9001",
        ]
    )
    assert serve.command == "serve"
    assert serve.transport == "streamable-http"
    assert serve.host == "0.0.0.0"
    assert serve.port == 9001
    listed = parser.parse_args(["tools", "list", "--url", "http://example.invalid/mcp"])
    assert listed.tools_command == "list"
    called = parser.parse_args(["tools", "call", "--tool", "web-search", "--arguments", '{"query":"x"}'])
    assert called.tools_command == "call"
    assert called.tool == "web-search"


def test_main_tools_list_and_call(capsys) -> None:
    client = MagicMock()
    client.list_tools = AsyncMock(return_value=[{"name": "web-search"}])
    client.call_tool = AsyncMock(return_value={"content": [{"type": "text", "text": "ok"}]})

    with patch("library_ioa.plugins.mcp.client.MCPClient", return_value=client):
        assert main(["tools", "list", "--url", "http://127.0.0.1:9001/mcp"]) == 0
        assert json.loads(capsys.readouterr().out) == [{"name": "web-search"}]
        assert main(["tools", "call", "--tool", "web-search", "--arguments", '{"query":"Apple"}']) == 0
        assert json.loads(capsys.readouterr().out)["content"][0]["text"] == "ok"
    client.call_tool.assert_called()


def test_main_tools_call_rejects_non_object_arguments() -> None:
    with pytest.raises(SystemExit):
        main(["tools", "call", "--tool", "web-search", "--arguments", '["not", "an", "object"]'])


def test_main_serve_stdio_and_http(tmp_path) -> None:
    factory = MagicMock()
    factory._tools = [{"name": "sample-tool"}]
    with patch("library_ioa.plugins.mcp.server.MCPToolServerFactory.from_manifest", return_value=factory):
        assert main(["serve", "--tool-manifest", str(tmp_path / "t.yaml")]) == 0
        factory.run.assert_called_with(transport="stdio")
        assert (
            main(
                [
                    "serve",
                    "--tool-manifest",
                    str(tmp_path / "t.yaml"),
                    "--transport",
                    "streamable-http",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "9001",
                    "--no-json-response",
                    "--no-stateless-http",
                ]
            )
            == 0
        )
        factory.run.assert_called_with(
            transport="streamable-http",
            host="127.0.0.1",
            port=9001,
            json_response=False,
            stateless_http=False,
        )


def test_main_module_entrypoint_imports() -> None:
    from library_ioa.plugins.mcp.server import __main__ as server_main

    assert callable(server_main.main)
