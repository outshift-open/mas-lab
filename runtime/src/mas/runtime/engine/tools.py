#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible tool definitions from agent manifest."""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.delegation import openai_delegation_tools

_TUTORIAL_TOOLS: dict[str, dict[str, Any]] = {
    "calculator": {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a mathematical expression.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    "verify_fact": {
        "type": "function",
        "function": {
            "name": "verify_fact",
            "description": "Verify a factual claim (prices, stocks, market data).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    "web-search": {
        "type": "function",
        "function": {
            "name": "web-search",
            "description": "Search the web for current information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
}


def tool_names_from_manifest(manifest: dict | None) -> list[str]:
    spec = (manifest or {}).get("spec") or {}
    tools = spec.get("tools") or []
    names: list[str] = []
    for item in tools:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("id")
            if name:
                names.append(str(name))
    return names


def openai_tools(manifest: dict | None) -> list[dict[str, Any]]:
    """Build OpenAI ``tools`` payload from manifest ``spec.tools`` list."""
    out: list[dict[str, Any]] = list(openai_delegation_tools(manifest))
    seen = {t["function"]["name"] for t in out if t.get("function")}
    for name in tool_names_from_manifest(manifest):
        if name in seen:
            continue
        if name in _TUTORIAL_TOOLS:
            out.append(_TUTORIAL_TOOLS[name])
        else:
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": f"Invoke tool {name}.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )
    return out
