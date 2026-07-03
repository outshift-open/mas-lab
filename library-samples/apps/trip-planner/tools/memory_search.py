#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Trip-planner memory-search tool backed by semantic memory plugin."""

from __future__ import annotations

from typing import Any

from mas.library.standard.plugins.memory.memory_semantic import SemanticMemoryPlugin


class MemorySearchTool:
    def on_collect_tools(self, **_: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": "memory-search",
                "description": "Search the agent semantic memory store.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]

    def on_execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        **_: Any,
    ) -> Any:
        if tool_name != "memory-search":
            return None
        q = str(arguments.get("query") or "").strip()
        if not q:
            return {"error": "empty query"}
        agent_id = getattr(ctx, "agent_id", None) or "default"
        from mas.runtime.boundary.memory.semantic import default_store_path

        mem = SemanticMemoryPlugin(
            db_path=str(default_store_path(str(agent_id))),
            context_inject=False,
        )
        mem.agent_id = str(agent_id)
        result = mem.read_memory("semantic", search=q)
        items = result.get("items", []) if isinstance(result, dict) else []
        mem.close()
        if not items:
            return {"query": q, "items": [], "message": f"no matches for {q!r}"}
        lines = []
        for item in items:
            key = item.get("key", "")
            content = str(item.get("content", ""))[:200]
            lines.append(f"- {key}: {content}")
        return {"query": q, "items": items, "text": "\n".join(lines)}
