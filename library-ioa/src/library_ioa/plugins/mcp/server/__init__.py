#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from functools import wraps
from inspect import Parameter, Signature
from pathlib import Path
from typing import Any, Dict, List

import yaml
from mas.runtime.manifest.schema.tool import ToolDocument
from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


def _python_type_for_schema(schema_type: str | None) -> type:
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    return mapping.get((schema_type or "").lower(), Any)


def _parameters_from_tool_doc(tool_doc: Any) -> list[dict[str, Any]]:
    spec_block = getattr(tool_doc, "spec", tool_doc)
    parameters: list[dict[str, Any]] = []
    for param in getattr(spec_block, "parameters", None) or []:
        if hasattr(param, "name"):
            parameters.append(
                {
                    "name": param.name,
                    "type": getattr(param, "type", "string") or "string",
                    "required": bool(getattr(param, "required", False)),
                }
            )
        elif isinstance(param, dict):
            parameters.append(
                {
                    "name": param.get("name"),
                    "type": param.get("type") or "string",
                    "required": bool(param.get("required", False)),
                }
            )
    return parameters


def _invoke_tool(tool_instance: Any, tool_name: str, arguments: dict[str, Any]) -> Any:
    if callable(getattr(tool_instance, "call_tool", None)):
        return tool_instance.call_tool(tool_name, arguments)
    return tool_instance.execute(**arguments)


def _wrapped_tool_fn(
    tool_name: str,
    description: str,
    parameters: list[dict[str, Any]],
    tool_instance: Any,
) -> Any:
    sig_params: list[Parameter] = []
    annotations: dict[str, Any] = {}
    for index, param in enumerate(parameters):
        name = str(param.get("name") or f"arg_{index}")
        python_type = _python_type_for_schema(str(param.get("type") or "string"))
        annotations[name] = python_type
        required = bool(param.get("required", False))
        default = Parameter.empty if required else None
        sig_params.append(Parameter(name, Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=python_type))

    def wrapped(**kwargs: Any) -> Any:
        return _invoke_tool(tool_instance, tool_name, kwargs)

    wrapped.__name__ = tool_name
    wrapped.__doc__ = description
    wrapped.__annotations__ = {**annotations, "return": Any}
    wrapped.__signature__ = Signature(sig_params, return_annotation=Any)
    return wrapped


def _tool_annotations(raw: Any) -> Any:
    if not raw:
        return None
    try:
        from mcp.types import ToolAnnotations

        return ToolAnnotations.model_validate(raw)
    except Exception:
        return None


def _tool_icons(raw: Any) -> Any:
    if not raw:
        return None
    try:
        from mcp.types import Icon

        return [Icon.model_validate(item) if not isinstance(item, Icon) else item for item in raw]
    except Exception:
        return None


class MCPToolServerFactory:
    """Factory for wrapping MAS tools in an MCP server."""

    def __init__(self, *, server_name: str = "mas-tool-server") -> None:
        self.server_name = server_name
        self._server = MCPServer(server_name)
        self._tools: List[Dict[str, Any]] = []

    @classmethod
    def from_manifest(cls, manifest_path: str | Path, *, tool_name: str | None = None) -> "MCPToolServerFactory":
        path = Path(manifest_path)
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError(f"Tool manifest {path} did not parse to a mapping.")

        tool_doc = ToolDocument.from_dict(doc)
        resolved_tool_name = tool_name or tool_doc.name
        if not resolved_tool_name:
            raise ValueError(f"Tool manifest {path} is missing metadata.name.")

        impl = (doc.get("spec") or {}).get("impl") or {}
        module_path = impl.get("module_path")
        if not module_path:
            raise ValueError(f"Tool manifest {path} is missing spec.impl.module_path.")

        module_file = path.parent / module_path
        if not module_file.exists():
            raise FileNotFoundError(f"Tool module not found: {module_file}")

        spec = importlib.util.spec_from_file_location(f"_mas_tool_{resolved_tool_name}", module_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load tool module from {module_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        class_name = impl.get("class_name")
        if not class_name:
            raise ValueError(f"Tool manifest {path} is missing spec.impl.class_name.")
        tool_class = getattr(module, class_name)
        tool_instance = tool_class()

        factory = cls(server_name=resolved_tool_name)
        factory._wrap_tool_instance(resolved_tool_name, tool_instance, tool_doc)
        return factory

    def _wrap_tool_instance(
        self,
        tool_name: str,
        tool_instance: Any,
        tool_doc: Any,
    ) -> None:
        from library_ioa.plugins.mcp.contract import mas_tool_document_to_mcp

        mcp_spec = mas_tool_document_to_mcp(tool_doc, tool_name)
        parameters = _parameters_from_tool_doc(tool_doc)
        description = str(mcp_spec.get("description") or tool_name)
        wrapped = _wrapped_tool_fn(tool_name, description, parameters, tool_instance)
        self.add_tool(
            {
                "name": tool_name,
                "description": description,
                "fn": wrapped,
                "parameters": parameters,
                "mcp": mcp_spec,
            }
        )

    def add_tool(self, tool_spec: Dict[str, Any]) -> None:
        self._tools.append(tool_spec)
        fn = tool_spec["fn"]
        name = str(tool_spec["name"])
        mcp_spec = tool_spec.get("mcp") or {}
        tool_annotations = _tool_annotations(mcp_spec.get("annotations"))
        icons = _tool_icons(mcp_spec.get("icons"))
        meta = mcp_spec.get("_meta") or mcp_spec.get("meta")

        @wraps(fn)
        def logged(*args: Any, **kwargs: Any) -> Any:
            logger.info("MCP tool call name=%s arguments=%s", name, kwargs or args)
            result = fn(*args, **kwargs)
            logger.info("MCP tool done name=%s", name)
            return result

        self._server.add_tool(
            logged,
            name=name,
            description=str(tool_spec.get("description") or ""),
            title=str(mcp_spec.get("title") or name),
            annotations=tool_annotations,
            icons=icons,
            meta=meta,
        )

    def run(self, transport: str = "stdio", **kwargs: Any) -> None:
        if transport == "stdio":
            self._server.run(transport="stdio")
            return
        if transport in {"sse", "streamable-http"}:
            self._server.run(transport=transport, **kwargs)
            return
        raise ValueError(f"Unsupported MCP transport: {transport}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mas-mcp", description="Serve MAS tool manifests over MCP.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Serve a MAS tool manifest over an MCP transport.")
    serve.add_argument("--tool-manifest", required=True, help="Path to a MAS Tool YAML manifest.")
    serve.add_argument("--tool", help="Optional tool name override when the manifest contains one tool.")
    serve.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default="stdio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--json-response",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="HTTP: JSON responses (default on; disable with --no-json-response).",
    )
    serve.add_argument(
        "--stateless-http",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="HTTP: stateless sessions (default on; disable with --no-stateless-http).",
    )

    tools_p = subparsers.add_parser("tools", help="Talk to a running MCP server as a client.")
    tools_sub = tools_p.add_subparsers(dest="tools_command", required=True)
    tools_list = tools_sub.add_parser("list", help="List tools advertised by the server.")
    tools_list.add_argument("--url", default="http://127.0.0.1:9001/mcp")
    tools_call = tools_sub.add_parser("call", help="Call a tool by name.")
    tools_call.add_argument("--url", default="http://127.0.0.1:9001/mcp")
    tools_call.add_argument("--tool", required=True)
    tools_call.add_argument("--arguments", default="{}", help="JSON object of tool arguments.")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "tools":
        import asyncio
        import json

        from library_ioa.plugins.mcp.client import MCPClient

        client = MCPClient(url=args.url)
        if args.tools_command == "list":
            tools = asyncio.run(client.list_tools())
            print(json.dumps(tools, indent=2))
            return 0
        payload = json.loads(args.arguments)
        if not isinstance(payload, dict):
            parser.error("--arguments must be a JSON object")
        result = asyncio.run(client.call_tool(args.tool, payload))
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.command == "serve":
        factory = MCPToolServerFactory.from_manifest(args.tool_manifest, tool_name=args.tool)
        if args.transport == "stdio":
            factory.run(transport="stdio")
            return 0

        logger.info(
            "Serving MCP %s on http://%s:%s/mcp tools=%s json_response=%s stateless_http=%s",
            args.transport,
            args.host,
            args.port,
            [t["name"] for t in factory._tools],
            args.json_response,
            args.stateless_http,
        )
        factory.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
            json_response=args.json_response,
            stateless_http=args.stateless_http,
        )
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
