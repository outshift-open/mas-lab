#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCP tool wire-format ↔ MAS tool-contract shapes.

MAS ``ToolContract.list_tools()`` / ``call_tool()`` are the runtime contract.
MCP ``tools/list`` / ``tools/call`` are the wire protocol. This module is the
only place that translates between them.

``call_tool(tool_name, arguments)`` is the required invocation. Optional
protocol options and advertise/result attributes are omitted when unset.

Not a ToolContract concern (provider spec / infra / SDK)
-----------------------------------------------------------------
- HTTP/SSE headers and auth (``spec.providers[].headers`` / infra)
- transport choice (stdio | streamable-http | sse)
- ListToolsResult ``ttlMs`` / ``cacheScope`` (list-response cache policy)
- caller-visible pagination: the plugin flattens ``nextCursor`` pages;
  ``list_tools(cursor=...)`` is optional on composite providers
- MCP ``add_tool(structured_output=True)`` requiring a Pydantic return type
  (SDK limitation; the contract carries ``output_schema`` as JSON Schema)
"""

from __future__ import annotations

from typing import Any


def as_mas_tool_spec(mcp_tool: dict[str, Any]) -> dict[str, Any]:
    """Translate one MCP ``Tool`` dict into a MAS ``list_tools`` entry."""
    schema = mcp_tool.get("inputSchema") or mcp_tool.get("input_schema") or mcp_tool.get("parameters") or {}
    spec: dict[str, Any] = {
        "name": str(mcp_tool.get("name") or ""),
        "description": str(mcp_tool.get("description") or ""),
        "parameters": schema if isinstance(schema, dict) else {"type": "object", "properties": {}},
    }
    title = mcp_tool.get("title")
    if title:
        spec["title"] = title
    output = mcp_tool.get("outputSchema") or mcp_tool.get("output_schema")
    if output:
        spec["output_schema"] = output
        spec["returns"] = output
    annotations = mcp_tool.get("annotations")
    if annotations:
        spec["annotations"] = annotations
        hints = annotations if isinstance(annotations, dict) else {}
        if hints.get("idempotentHint") is True or hints.get("idempotent_hint") is True:
            spec["idempotent"] = True
        if "readOnlyHint" in hints or "read_only_hint" in hints:
            spec["read_only"] = bool(hints.get("readOnlyHint", hints.get("read_only_hint")))
        if "destructiveHint" in hints or "destructive_hint" in hints:
            spec["destructive"] = bool(hints.get("destructiveHint", hints.get("destructive_hint")))
        if "openWorldHint" in hints or "open_world_hint" in hints:
            spec["open_world"] = bool(hints.get("openWorldHint", hints.get("open_world_hint")))
        hint_title = hints.get("title")
        if hint_title and "title" not in spec:
            spec["title"] = hint_title
    icons = mcp_tool.get("icons")
    if icons:
        spec["icons"] = icons
    execution = mcp_tool.get("execution")
    if isinstance(execution, dict):
        spec["execution"] = execution
        task_support = execution.get("taskSupport") or execution.get("task_support")
        if task_support:
            spec["task_support"] = task_support
    elif execution:
        spec["execution"] = execution
    meta = mcp_tool.get("_meta") or mcp_tool.get("meta")
    if meta:
        spec["meta"] = meta
    return spec


def as_mas_tool_result(payload: Any) -> dict[str, Any]:
    """Translate an MCP ``CallToolResult`` into a ``ToolResultEnvelope`` dict."""
    if not isinstance(payload, dict):
        return {"status": "ok", "result": payload, "is_error": False}

    is_error = bool(payload.get("isError") or payload.get("is_error"))
    structured = payload.get("structuredContent")
    if structured is None:
        structured = payload.get("structured_content")
    content = payload.get("content")
    text_parts: list[str] = []
    other_parts: list[Any] = []
    content_parts: list[dict[str, Any]] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                content_parts.append(item)
                if item.get("type") == "text" and "text" in item:
                    text_parts.append(str(item.get("text") or ""))
                else:
                    other_parts.append(item)
            elif item is not None:
                other_parts.append(item)
    elif isinstance(content, dict):
        content_parts.append(content)
        other_parts.append(content)
    elif content is not None:
        other_parts.append(content)

    if structured is not None:
        result: Any = structured
    elif text_parts:
        result = "".join(text_parts)
    elif other_parts:
        result = other_parts[0] if len(other_parts) == 1 else other_parts
    else:
        result = payload.get("result")

    result_type = str(payload.get("resultType") or payload.get("result_type") or "complete")
    meta = payload.get("_meta") or payload.get("meta") or {}
    out: dict[str, Any] = {
        "status": "error" if is_error else "ok",
        "result": result,
        "is_error": is_error,
    }
    if content_parts:
        text_only = bool(text_parts) and not other_parts and len(content_parts) == len(text_parts)
        if not text_only:
            out["content"] = content_parts
    if structured is not None:
        out["structured_content"] = structured
    if result_type and result_type != "complete":
        out["result_type"] = result_type
    if meta:
        out["meta"] = meta
    return out


def mas_tool_document_to_mcp(tool_doc: Any, name: str) -> dict[str, Any]:
    """Advertise a MAS ``kind: Tool`` document as an MCP ``Tool`` dict."""
    spec_block = getattr(tool_doc, "spec", None)
    source = spec_block if spec_block is not None else tool_doc
    to_server = getattr(source, "to_tool_server_spec", None)
    if callable(to_server):
        advertised = dict(to_server(name))
        if advertised.get("description") or advertised.get("inputSchema"):
            metadata = getattr(tool_doc, "metadata", None) or {}
            if isinstance(metadata, dict) and not advertised.get("title"):
                title = metadata.get("description")
                if title:
                    advertised["title"] = title
            return advertised

    description = str(getattr(source, "description", None) or getattr(tool_doc, "description", "") or "")
    to_schema = getattr(source, "to_json_schema", None) or getattr(tool_doc, "to_json_schema", None)
    input_schema = to_schema() if callable(to_schema) else {"type": "object", "properties": {}}
    advertised: dict[str, Any] = {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
    }
    metadata = getattr(tool_doc, "metadata", None) or {}
    title = getattr(source, "title", None)
    if not title and isinstance(metadata, dict):
        title = metadata.get("description")
    if title:
        advertised["title"] = title
    annotations: dict[str, Any] = {}
    if bool(getattr(source, "idempotent", False) or getattr(tool_doc, "idempotent", False)):
        annotations["idempotentHint"] = True
    for attr, hint in (
        ("read_only", "readOnlyHint"),
        ("destructive", "destructiveHint"),
        ("open_world", "openWorldHint"),
    ):
        value = getattr(source, attr, None)
        if value is not None:
            annotations[hint] = bool(value)
    if annotations:
        advertised["annotations"] = annotations
    output = getattr(source, "output_schema", None) or getattr(source, "returns", None)
    if isinstance(output, dict) and output:
        advertised["outputSchema"] = output
    icons = getattr(source, "icons", None)
    if icons:
        advertised["icons"] = list(icons)
    task_support = getattr(source, "task_support", None)
    if task_support:
        advertised["execution"] = {"taskSupport": task_support}
    meta = getattr(source, "meta", None)
    if meta:
        advertised["_meta"] = dict(meta)
    return advertised
