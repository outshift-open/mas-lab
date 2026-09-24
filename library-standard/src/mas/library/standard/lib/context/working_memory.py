#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-turn working-memory slice for the assembler plugin."""

from __future__ import annotations

from typing import Any

from mas.library.standard.lib.context.payload import start_of_tool_group
from mas.library.standard.lib.context.spec import context_manager_spec
from mas.runtime.spec.defaults import DEFAULT_WORKING_MEMORY_MESSAGES


def working_memory_slice_limit(manifest: dict | None) -> int:
    """Max in-turn working-memory messages kept for assembly (0 = unbounded)."""
    cm = context_manager_spec(manifest)
    params = cm.get("params") or {}
    for key in ("working_memory_messages", "max_in_turn_messages", "max_messages"):
        raw = params.get(key)
        if raw is not None:
            try:
                return max(0, int(raw))
            except (TypeError, ValueError):
                break
    return DEFAULT_WORKING_MEMORY_MESSAGES


def bounded_working_memory_tail(
    messages: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Keep at most the last *limit* messages, never splitting a tool-call group."""
    if limit <= 0 or len(messages) <= limit:
        return list(messages)
    return list(messages[start_of_tool_group(messages, len(messages) - limit) :])
