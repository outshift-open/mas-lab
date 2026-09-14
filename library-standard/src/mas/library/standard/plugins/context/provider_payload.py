#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Provider-safe history helpers for context_manager plugins (not a registry plugin)."""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.context.provider_invariant import assert_provider_payload, tool_call_pairs

__all__ = [
    "assert_provider_payload",
    "sanitize_provider_messages",
    "tool_call_pairs",
]


def sanitize_provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []
    return _sanitize_completed(messages)


def _repair_tool_call_bindings(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    unresolved: set[str] = set()

    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            repaired.append(msg)
            unresolved = {str(c.get("id")) for c in msg["tool_calls"] if c.get("id")}
            continue

        if msg.get("role") == "tool" and unresolved:
            tool_id = str(msg.get("tool_call_id") or "")
            if tool_id not in unresolved:
                rebound = dict(msg)
                rebound["tool_call_id"] = sorted(unresolved)[0]
                repaired.append(rebound)
                unresolved.discard(rebound["tool_call_id"])
                continue
            unresolved.discard(tool_id)
            repaired.append(msg)
            continue

        if msg.get("role") != "tool":
            unresolved = set()
        repaired.append(msg)
    return repaired


def _sanitize_completed(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not messages:
        return []

    messages = _repair_tool_call_bindings(messages)
    declared = tool_call_pairs(messages)[0]
    without_orphan_tools = [
        msg for msg in messages if msg.get("role") != "tool" or str(msg.get("tool_call_id") or "") in declared
    ]

    sanitized: list[dict[str, Any]] = []
    i = 0
    while i < len(without_orphan_tools):
        msg = without_orphan_tools[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            call_ids = {str(c.get("id")) for c in msg["tool_calls"] if c.get("id")}
            j = i + 1
            found: set[str] = set()
            while j < len(without_orphan_tools) and without_orphan_tools[j].get("role") == "tool":
                tool_id = without_orphan_tools[j].get("tool_call_id")
                if tool_id:
                    found.add(str(tool_id))
                j += 1
            if call_ids and call_ids <= found:
                sanitized.extend(without_orphan_tools[i:j])
                i = j
                continue
            stripped = {k: v for k, v in msg.items() if k != "tool_calls"}
            if str(stripped.get("content") or "").strip():
                sanitized.append(stripped)
            i += 1
            continue
        sanitized.append(msg)
        i += 1
    return sanitized
