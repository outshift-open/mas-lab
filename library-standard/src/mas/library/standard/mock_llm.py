#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Mock LLM helpers — schema-driven tool stubs (no hardcoded tool ids)."""

from __future__ import annotations

import re
from typing import Any

_ARITH_EXPR = re.compile(r"(\d+\s*[\+\-\*/%]+\s*\d+|\d[\d\s+\-*/().%]*\d)")

__all__ = [
    "openai_tools_to_specs",
    "pick_tool_call",
    "stub_arguments",
]


def openai_tools_to_specs(tools: list[dict[str, Any]] | None) -> list[tuple[str, dict[str, Any]]]:
    specs: list[tuple[str, dict[str, Any]]] = []
    for item in tools or []:
        fn = item.get("function") if isinstance(item, dict) else None
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not name:
            continue
        params = fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {}
        specs.append((str(name), params))
    return specs


def stub_arguments(params: dict[str, Any], user: str) -> dict[str, Any]:
    """Build minimal arguments from a tool JSON-schema ``parameters`` object."""
    props = params.get("properties") if isinstance(params.get("properties"), dict) else {}
    required = list(params.get("required") or [])
    out: dict[str, Any] = {}
    for key in required:
        prop = props.get(key) if isinstance(props.get(key), dict) else {}
        ptype = prop.get("type", "string")
        if key == "expression" or (ptype == "string" and "expression" in key.lower()):
            m = _ARITH_EXPR.search(user)
            out[key] = (m.group(1).strip() if m else "") or "1+1"
        elif key == "query" or "query" in key.lower():
            out[key] = user.strip()[:200] or "general knowledge"
        elif ptype == "string":
            examples = prop.get("examples") or []
            out[key] = str(examples[0]) if examples else user.strip()[:120] or "test"
        elif ptype in ("number", "integer"):
            out[key] = 0
        elif ptype == "boolean":
            out[key] = False
        else:
            out[key] = user.strip()[:120] or "test"
    return out


def pick_tool_call(
    user: str,
    tool_specs: list[tuple[str, dict[str, Any]]],
) -> tuple[str, dict[str, Any]] | None:
    """Choose a tool and stub args from declared schemas (no hardcoded tool ids)."""
    if not tool_specs or not user.strip():
        return None

    props_by_tool: list[tuple[str, dict[str, Any], set[str]]] = []
    for name, params in tool_specs:
        props = params.get("properties") if isinstance(params.get("properties"), dict) else {}
        props_by_tool.append((name, params, set(props)))

    if re.search(r"\d", user) and re.search(r"[\+\-\*/%]", user):
        for name, params, keys in props_by_tool:
            if "expression" in keys:
                return name, stub_arguments(params, user)

    for name, params, keys in props_by_tool:
        if "query" in keys:
            return name, stub_arguments(params, user)

    name, params = tool_specs[0]
    args = stub_arguments(params, user)
    return name, args if args else {}
