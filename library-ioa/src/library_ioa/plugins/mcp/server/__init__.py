from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml
from mcp.server.mcpserver import MCPServer

from mas.runtime.manifest.schema.tool import ToolDocument

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

        params = []
        for entry in (doc.get("spec") or {}).get("parameters", []):
            if isinstance(entry, dict):
                params.append(entry)

        factory = cls(server_name=resolved_tool_name)
        factory._wrap_tool_instance(resolved_tool_name, tool_instance, tool_doc.description or resolved_tool_name, params)
        return factory

    def _wrap_tool_instance(
        self,
        tool_name: str,
        tool_instance: Any,
        description: str,
        parameters: list[dict[str, Any]],
    ) -> None:
        annotations: dict[str, Any] = {}
        defaults: dict[str, Any] = {}
        body_parts: list[str] = ["def _wrapped_tool("]
        param_names: list[str] = []

        for index, param in enumerate(parameters):
            name = str(param.get("name") or f"arg_{index}")
            schema_type = str(param.get("type") or "string")
            python_type = _python_type_for_schema(schema_type)
            annotations[name] = python_type
            param_names.append(name)
            required = bool(param.get("required", True))
            if required:
                body_parts.append(f"{name}: {python_type.__name__}, ")
            else:
                body_parts.append(f"{name}: {python_type.__name__} | None = None, ")
        body_parts.append(") -> dict:\n")
        body_parts.append("    return tool_instance.execute(**locals())\n")
        namespace = {"tool_instance": tool_instance, "Any": Any, "Dict": Dict, "List": List}
        exec("".join(body_parts), namespace)
        wrapped = namespace["_wrapped_tool"]
        wrapped.__annotations__ = annotations
        wrapped.__name__ = tool_name
        wrapped.__doc__ = description

        self.add_tool({
            "name": tool_name,
            "description": description,
            "fn": wrapped,
            "parameters": parameters,
        })

    def add_tool(self, tool_spec: Dict[str, Any]) -> None:
        self._tools.append(tool_spec)
        fn = tool_spec["fn"]
        self._server.add_tool(
            fn,
            name=str(tool_spec["name"]),
            description=str(tool_spec.get("description") or ""),
            title=str(tool_spec["name"]),
        )

    def run(self, transport: str = "stdio", **kwargs: Any) -> None:
        if transport == "stdio":
            self._server.run(transport="stdio")
            return
        if transport in {"sse", "streamable-http"}:
            self._server.run(transport=transport, **kwargs)
            return
        raise ValueError(f"Unsupported MCP transport: {transport}")

    async def run_server(self) -> None:
        logger.info("Starting MCP server with %d tools", len(self._tools))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mas-mcp", description="Serve MAS tool manifests over MCP.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Serve a MAS tool manifest over an MCP transport.")
    serve.add_argument("--tool-manifest", required=True, help="Path to a MAS Tool YAML manifest.")
    serve.add_argument("--tool", help="Optional tool name override when the manifest contains one tool.")
    serve.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--json-response", action="store_true")
    serve.add_argument("--stateless-http", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        factory = MCPToolServerFactory.from_manifest(args.tool_manifest, tool_name=args.tool)
        if args.transport == "stdio":
            factory.run(transport="stdio")
            return 0

        factory.run(
            transport="streamable-http",
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
