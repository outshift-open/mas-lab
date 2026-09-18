#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""memory-search tool — active retrieval against semantic memory."""

from __future__ import annotations

from typing import Any

from mas.library.standard.plugins.memory.memory_semantic import SemanticMemoryPlugin


class MemorySearchTool:
    def on_collect_tools(self, **_: Any) -> list[dict[str, Any]]:
        search = {
            "name": "memory-search",
            "description": "Search the agent semantic memory store.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
        store_params = {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Fact or preference to remember."},
                "query": {"type": "string", "description": "Alias for content."},
                "source": {"type": "string"},
            },
        }
        return [
            search,
            {
                "name": "memory_store",
                "description": "Store a fact or user preference in semantic memory.",
                "parameters": store_params,
            },
        ]

    def _plugin(self, ctx: Any) -> SemanticMemoryPlugin:
        agent_id = getattr(ctx, "agent_id", None) or "default"
        from mas.runtime.boundary.memory.semantic import default_store_path

        mem = SemanticMemoryPlugin(
            db_path=str(default_store_path(str(agent_id))),
            context_inject=False,
        )
        mem.agent_id = str(agent_id)
        return mem

    def on_execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        **_: Any,
    ) -> Any:
        if tool_name == "memory_store":
            content = str(arguments.get("content") or arguments.get("query") or "").strip()
            if not content:
                return {"error": "empty content"}
            mem = self._plugin(ctx)
            try:
                return mem.write_memory(
                    "semantic",
                    {
                        "content": content,
                        "source": str(arguments.get("source") or "user_preference"),
                    },
                )
            finally:
                mem.close()
        if tool_name != "memory-search":
            return None
        q = str(arguments.get("query") or "").strip()
        if not q:
            return {"error": "empty query"}
        mem = self._plugin(ctx)
        try:
            result = mem.read_memory("semantic", search=q)
        finally:
            mem.close()
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items:
            return {"query": q, "items": [], "message": f"no matches for {q!r}"}
        lines = []
        for item in items:
            key = item.get("key", "")
            content = str(item.get("content", ""))[:200]
            lines.append(f"- {key}: {content}")
        return {"query": q, "items": items, "text": "\n".join(lines)}
