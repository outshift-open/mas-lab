#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible tool definitions from agent manifest."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from mas.runtime.boundary.delegation import delegation_targets, openai_delegation_tools

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


def tool_name_from_ref(ref: str, *, base_dir: Path | None) -> str | None:
    if not ref or not base_dir:
        return None
    root = base_dir.resolve()
    path = (root / ref).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not isinstance(doc, dict):
        return None
    name = (doc.get("metadata") or {}).get("name")
    return str(name) if name else None


def resolve_manifest_tool_refs(
    manifest: dict[str, Any],
    base_dir: Path | None,
    *,
    inplace: bool = False,
) -> dict[str, Any]:
    """Expand ``spec.tools[].ref`` entries to logical tool names."""
    if not base_dir:
        return manifest
    tools = (manifest.get("spec") or {}).get("tools")
    if not isinstance(tools, list):
        return manifest
    resolved: list[Any] = []
    changed = False
    for item in tools:
        if isinstance(item, dict) and item.get("ref") and not (item.get("name") or item.get("id")):
            name = tool_name_from_ref(str(item["ref"]), base_dir=base_dir)
            if name:
                resolved.append({**item, "name": name})
                changed = True
                continue
        if inplace:
            resolved.append(item)
        else:
            resolved.append(copy.deepcopy(item) if isinstance(item, dict) else item)
    if not changed:
        return manifest
    if inplace:
        manifest.setdefault("spec", {})["tools"] = resolved
        return manifest
    out = copy.deepcopy(manifest)
    out.setdefault("spec", {})["tools"] = resolved
    return out


def _manifest_agent_id(manifest: dict | None, agent_id: str | None) -> str | None:
    if agent_id:
        return agent_id
    name = ((manifest or {}).get("metadata") or {}).get("name")
    return str(name) if name else None


def tool_names_from_manifest(manifest: dict | None, *, base_dir: Path | None = None) -> list[str]:
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
                continue
            ref = item.get("ref")
            if isinstance(ref, str):
                resolved = tool_name_from_ref(ref, base_dir=base_dir)
                if resolved:
                    names.append(resolved)
    return names


def openai_tools(
    manifest: dict | None,
    *,
    base_dir: Path | None = None,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build OpenAI ``tools`` from manifest ``spec.tools`` and MAS delegation topology."""
    aid = _manifest_agent_id(manifest, agent_id)
    out: list[dict[str, Any]] = list(openai_delegation_tools(manifest, agent_id=aid))
    seen = {t["function"]["name"] for t in out if t.get("function")}
    for name in tool_names_from_manifest(manifest, base_dir=base_dir):
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
