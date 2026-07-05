#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve tool names for native observability events."""

from __future__ import annotations

from typing import Any


def coerce_tool_name(value: Any) -> str:
    """Normalize tool_name; JSON ``null`` and empty strings become ``""``."""
    if value is None:
        return ""
    text = str(value).strip()
    return text


def resolve_tool_name(payload: dict[str, Any], *, default: str = "tool") -> str:
    """Best-effort tool name from boundary/engine-io payload fields."""
    name = coerce_tool_name(payload.get("tool_name"))
    if name:
        return name
    op = str(payload.get("op") or "").strip()
    if op and op not in {"TOOL_CALL", "LLM_CALL", "MEMORY_OP"}:
        return op
    activity = str(payload.get("activity") or "").strip()
    if activity:
        return activity
    tools = payload.get("tools")
    if isinstance(tools, list) and tools:
        first = tools[0]
        if isinstance(first, dict):
            nested = coerce_tool_name(first.get("tool_name") or first.get("name"))
            if nested:
                return nested
        elif first is not None:
            nested = coerce_tool_name(first)
            if nested:
                return nested
    return default


__all__ = ["coerce_tool_name", "resolve_tool_name"]
