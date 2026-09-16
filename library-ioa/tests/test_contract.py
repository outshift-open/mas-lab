#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from library_ioa.plugins.mcp.contract import (
    as_mas_tool_result,
    as_mas_tool_spec,
    mas_tool_document_to_mcp,
)
from mas.runtime.manifest.schema.tool import ToolDocument


def test_as_mas_tool_spec_maps_full_mcp_tool() -> None:
    spec = as_mas_tool_spec(
        {
            "name": "web-search",
            "title": "Web Search",
            "description": "Search the web",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            },
            "outputSchema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            "annotations": {
                "idempotentHint": True,
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": True,
                "title": "ignored-if-top-title-present",
            },
            "icons": [{"src": "https://example.invalid/icon.png", "mimeType": "image/png"}],
            "execution": {"taskSupport": "optional"},
            "_meta": {"vendor": "ioa"},
        }
    )
    assert spec["name"] == "web-search"
    assert spec["title"] == "Web Search"
    assert spec["description"] == "Search the web"
    assert spec["parameters"]["required"] == ["query"]
    assert spec["output_schema"]["properties"]["answer"]["type"] == "string"
    assert spec["returns"] == spec["output_schema"]
    assert spec["idempotent"] is True
    assert spec["read_only"] is True
    assert spec["open_world"] is True
    assert spec["destructive"] is False
    assert spec["icons"][0]["src"] == "https://example.invalid/icon.png"
    assert spec["execution"]["taskSupport"] == "optional"
    assert spec["meta"] == {"vendor": "ioa"}


def test_as_mas_tool_spec_snake_aliases_and_annotation_title() -> None:
    spec = as_mas_tool_spec(
        {
            "name": "calc",
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "number"},
            "annotations": {"idempotent_hint": True, "read_only_hint": True, "title": "Calculator"},
            "meta": {"k": "v"},
        }
    )
    assert spec["parameters"]["type"] == "object"
    assert spec["returns"] == {"type": "number"}
    assert spec["idempotent"] is True
    assert spec["read_only"] is True
    assert spec["title"] == "Calculator"
    assert spec["meta"] == {"k": "v"}


def test_as_mas_tool_spec_non_dict_schema_falls_back() -> None:
    spec = as_mas_tool_spec({"name": "x", "parameters": "not-a-schema"})
    assert spec["parameters"] == {"type": "object", "properties": {}}


def test_as_mas_tool_result_text_and_non_dict() -> None:
    assert as_mas_tool_result("ok") == {"status": "ok", "result": "ok", "is_error": False}
    mapped = as_mas_tool_result({"content": [{"type": "text", "text": "4"}]})
    assert mapped == {"status": "ok", "result": "4", "is_error": False}


def test_as_mas_tool_result_structured_and_non_text_parts() -> None:
    mapped = as_mas_tool_result(
        {
            "isError": False,
            "structuredContent": {"answer": 4},
            "content": [
                {"type": "text", "text": "ignored-when-structured"},
                {"type": "image", "data": "aaa", "mimeType": "image/png"},
                {"type": "audio", "data": "bbb", "mimeType": "audio/wav"},
                {"type": "resource_link", "uri": "file://x", "name": "x"},
            ],
            "resultType": "complete",
            "_meta": {"trace": "1"},
        }
    )
    assert mapped["result"] == {"answer": 4}
    assert mapped["is_error"] is False
    assert mapped["structured_content"] == {"answer": 4}
    assert mapped["content"][1]["type"] == "image"
    assert mapped["meta"] == {"trace": "1"}
    assert "result_type" not in mapped


def test_as_mas_tool_result_error_image_only_and_input_required() -> None:
    mapped = as_mas_tool_result(
        {
            "is_error": True,
            "content": [{"type": "image", "data": "xyz", "mimeType": "image/png"}],
            "result_type": "input_required",
            "meta": {"elicit": True},
        }
    )
    assert mapped["status"] == "error"
    assert mapped["is_error"] is True
    assert mapped["result"]["type"] == "image"
    assert mapped["result_type"] == "input_required"
    assert mapped["content"][0]["type"] == "image"
    assert mapped["meta"] == {"elicit": True}


def test_as_mas_tool_result_multiple_non_text_without_structured() -> None:
    mapped = as_mas_tool_result(
        {
            "content": [
                {"type": "resource", "resource": {"uri": "a"}},
                {"type": "resource", "resource": {"uri": "b"}},
            ]
        }
    )
    assert isinstance(mapped["result"], list)
    assert len(mapped["result"]) == 2


def test_mas_tool_document_to_mcp_uses_spec_not_metadata_description() -> None:
    doc = ToolDocument.from_dict(
        {
            "apiVersion": "mas/v1",
            "kind": "Tool",
            "metadata": {"name": "sample-tool", "description": "Catalogue label"},
            "spec": {
                "description": "Adds two integers",
                "parameters": [
                    {"name": "a", "type": "integer", "required": True},
                    {"name": "b", "type": "integer", "required": True},
                ],
                "returns": {"type": "integer", "description": "sum"},
                "idempotent": True,
                "impl": {"module_path": "./x.py", "class_name": "X"},
            },
        }
    )
    advertised = mas_tool_document_to_mcp(doc, "sample-tool")
    assert advertised["name"] == "sample-tool"
    assert advertised["title"] == "Catalogue label"
    assert advertised["description"] == "Adds two integers"
    assert advertised["inputSchema"]["required"] == ["a", "b"]
    assert advertised["outputSchema"]["type"] == "integer"
    assert advertised["annotations"]["idempotentHint"] is True


def test_mas_tool_document_to_mcp_optional_spec_attributes() -> None:
    doc = ToolDocument.from_dict(
        {
            "apiVersion": "mas/v1",
            "kind": "Tool",
            "metadata": {"name": "web-search"},
            "spec": {
                "description": "Search",
                "title": "Web Search",
                "read_only": True,
                "open_world": True,
                "task_support": "optional",
                "icons": [{"src": "https://example.invalid/i.png", "mime_type": "image/png"}],
                "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
                "meta": {"vendor": "ioa"},
                "impl": {"module_path": "./x.py", "class_name": "X"},
            },
        }
    )
    advertised = mas_tool_document_to_mcp(doc, "web-search")
    assert advertised["title"] == "Web Search"
    assert advertised["annotations"]["readOnlyHint"] is True
    assert advertised["annotations"]["openWorldHint"] is True
    assert advertised["execution"]["taskSupport"] == "optional"
    assert advertised["icons"][0]["src"] == "https://example.invalid/i.png"
    assert advertised["outputSchema"]["properties"]["answer"]["type"] == "string"
    assert advertised["_meta"] == {"vendor": "ioa"}
