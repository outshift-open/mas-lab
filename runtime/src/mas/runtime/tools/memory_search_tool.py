# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Memory search tool — exposes semantic memory search as an agent tool.

OpenClaw equivalence:
- Part of ``group:memory`` tool group
- ``memory_search`` tool: returns snippet text (<=700 chars), file path,
  line range, score
- Agent can invoke this tool to search its own long-term memory

Also includes ``memory_get`` for reading specific memory files.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mas.runtime.contracts.tool_contract import ToolContract
from mas.runtime.contracts.memory_contract import MemoryContract

logger = logging.getLogger(__name__)

# Default max snippet chars (same as OpenClaw)
DEFAULT_MAX_SNIPPET_CHARS = 700


class MemorySearchTool(ToolContract):
    """Search the agent's semantic memory for relevant information.

    Accepts any :class:`~mas.runtime.contracts.memory_contract.MemoryContract`
    backend at construction.  Uses the stable ``read_memory("semantic", {...})``
    contract path exclusively — the single supported interface.  Backends
    that want to return richer results (scores, citations) should do so by
    overriding ``read_memory("semantic", ...)`` directly; there is no
    out-of-band ``search()`` path.
    """

    def __init__(
        self,
        memory: Optional[MemoryContract] = None,
        citation_formatter: Optional[Any] = None,
    ) -> None:
        if memory is not None and not isinstance(memory, MemoryContract):
            raise TypeError(
                f"MemorySearchTool requires a MemoryContract, got {type(memory).__name__}. "
                "Pass a MemoryProviderPlugin or any other MemoryContract implementation."
            )
        self._memory = memory
        self._formatter = citation_formatter

    # Keep legacy setter name for backward compatibility with existing wiring code
    def set_memory_plugin(self, memory: MemoryContract) -> None:
        self._memory = memory

    def set_citation_formatter(self, formatter: Any) -> None:
        self._formatter = formatter

    def get_name(self) -> str:
        return "memory_search"

    def get_description(self) -> str:
        return (
            "Search the agent's long-term memory for relevant information. "
            "Returns text snippets from previously indexed documents, "
            "conversations, and memory files ranked by relevance."
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 6)",
                    "default": 6,
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: filter by source path prefixes",
                },
            },
            "required": ["query"],
        }

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        query = kwargs.get("query", "")
        if not query:
            return {"error": "query parameter is required"}

        if self._memory is None:
            return {"error": "memory not configured"}

        max_results = int(kwargs.get("max_results", 6))
        sources = kwargs.get("sources")

        try:
            kw: Dict[str, Any] = {"search": query, "limit": max_results}
            if sources:
                kw["sources"] = sources
            raw = self._memory.read_memory("semantic", **kw)
            # Normalise to list[{text, source, score, key}] for uniform downstream handling.
            # key / doc_id is preserved for provenance tracking (eval pipelines compare
            # retrieved doc_ids against expected_facts ground truth).
            items = raw.get("items", []) if isinstance(raw, dict) else []
            results = [
                {
                    "text": item.get("content", ""),
                    "source": (
                        item.get("source")
                        or (item.get("metadata") or {}).get("source", "")
                    ),
                    "score": (
                        item.get("score")
                        or (item.get("metadata") or {}).get("score", 0.0)
                    ),
                    "key": item.get("key") or item.get("doc_id") or "",
                }
                for item in items
            ]
        except Exception as exc:
            logger.debug("Memory search failed", exc_info=True)
            return {"error": f"search failed: {exc}"}

        # Format with citation formatter if available
        if self._formatter is not None:
            formatted = self._formatter.format_results(results)
            return {
                "results": results,
                "formatted": formatted,
                "count": len(results),
            }

        return {
            "results": [
                {
                    "text": r.get("text", "")[:DEFAULT_MAX_SNIPPET_CHARS],
                    "source": r.get("source", ""),
                    "score": r.get("score", 0.0),
                    "key": r.get("key", ""),
                }
                for r in results
            ],
            "count": len(results),
        }


class MemoryGetTool(ToolContract):
    """Read a specific memory file by path.

    Accepts any :class:`~mas.runtime.contracts.memory_contract.MemoryContract` backend.
    """

    def __init__(self, memory: Optional[MemoryContract] = None) -> None:
        self._memory = memory

    def set_memory_plugin(self, memory: MemoryContract) -> None:
        self._memory = memory

    def get_name(self) -> str:
        return "memory_get"

    def get_description(self) -> str:
        return (
            "Read a specific document or memory file from the agent's memory. "
            "Provide the source path or key of the document to retrieve."
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The source path or document key to retrieve",
                },
            },
            "required": ["key"],
        }

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        key = kwargs.get("key", "")
        if not key:
            return {"error": "key parameter is required"}

        if self._memory is None:
            return {"error": "memory plugin not configured"}

        try:
            result = self._memory.read_memory("semantic", search=key, limit=1)
            items = result.get("items", [])
            if not items:
                return {"error": f"no document found for key: {key}"}
            return {"content": items[0].get("content", ""), "key": key}
        except Exception as exc:
            logger.debug("Memory read failed for key %s", key, exc_info=True)
            return {"error": f"read failed: {exc}"}


class MemoryStoreTool(ToolContract):
    """Store a fact or preference in the agent's long-term memory.

    Accepts any :class:`~mas.runtime.contracts.memory_contract.MemoryContract` backend
    that supports ``write_memory()``.
    """

    def __init__(self, memory: Optional[MemoryContract] = None) -> None:
        self._memory = memory

    def set_memory_plugin(self, memory: MemoryContract) -> None:
        self._memory = memory

    def get_name(self) -> str:
        return "memory_store"

    def get_description(self) -> str:
        return (
            "Store a fact, preference, or correction in the agent's long-term memory. "
            "Use this when the user shares a preference, corrects you, or provides "
            "information that should be remembered for future interactions."
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact or preference to store (plain text)",
                },
                "source": {
                    "type": "string",
                    "description": "Short label for the origin, e.g. 'user_preference', 'correction'",
                    "default": "agent_stored",
                },
            },
            "required": ["content"],
        }

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        content = kwargs.get("content", "").strip()
        if not content:
            return {"error": "content parameter is required"}

        if self._memory is None:
            return {"error": "memory plugin not configured"}

        source = kwargs.get("source", "agent_stored")

        try:
            doc_id = self._memory.index_document(
                source=source,
                content=content,
            )
            return {"status": "stored", "doc_id": doc_id}
        except Exception as exc:
            logger.warning("Memory store failed: %s", exc, exc_info=True)
            return {"error": f"store failed: {exc}"}


class MemoryToolProvider(ToolContract):
    """Combined provider exposing memory_search, memory_get, and memory_store.

    This is the canonical entry point loaded by the flavour tool_providers
    for ``memory-search``.  All three tools share a single memory backend.
    """

    def __init__(self, memory_plugin: Optional[Any] = None) -> None:
        # Create children FIRST so the _memory setter can propagate.
        self._search = MemorySearchTool(memory_plugin)
        self._get = MemoryGetTool(memory_plugin)
        self._store = MemoryStoreTool(memory_plugin)
        self._tools = {
            "memory_search": self._search,
            "memory_get": self._get,
            "memory_store": self._store,
        }
        # Store backend (bypasses setter since children already have it)
        self.__dict__["_memory_backend"] = memory_plugin

    @property
    def _memory(self) -> Optional[Any]:
        return self.__dict__.get("_memory_backend")

    @_memory.setter
    def _memory(self, value: Any) -> None:
        self.__dict__["_memory_backend"] = value
        # Propagate to child tools (defensive: getattr for init ordering)
        for attr in ("_search", "_get", "_store"):
            tool = getattr(self, attr, None)
            if tool is not None and hasattr(tool, "_memory"):
                tool._memory = value

    def get_name(self) -> str:
        return "memory_search"  # primary tool name for legacy compat

    def get_description(self) -> str:
        return self._search.get_description()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return self._search.get_parameters_schema()

    def on_collect_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.get_name(),
                "description": t.get_description(),
                "parameters": t.get_parameters_schema(),
            }
            for t in self._tools.values()
        ]

    def on_execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tool = self._tools.get(tool_name)
        if tool is None:
            return None
        return tool.execute(**arguments)

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        return self._search.execute(**kwargs)
