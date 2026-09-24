#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Dispatch LLM ``messages[]`` assembly and turn-commit compact to ``spec.assembler``.

The kernel does not choose history/trim policy. It instantiates the registry
``assembler`` (default ``assembler``), asserts layer-1 pairing,
and records assembly telemetry. After each turn it asks the same plugin to
rewrite stored history to the context manager's recency cap.
"""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.context.assembly_cache import cached_assembler
from mas.runtime.boundary.context.provider_invariant import assert_provider_payload
from mas.runtime.boundary.context.telemetry import record_context_assembly


def _openai_tool_names(tools: list[dict[str, Any]] | None) -> list[str] | None:
    """Function names from an OpenAI ``tools`` array. ``None`` if not recorded."""
    if tools is None:
        return None
    names: list[str] = []
    for tool in tools:
        fn = tool.get("function") if isinstance(tool, dict) else None
        name = str((fn or {}).get("name") or "") if isinstance(fn, dict) else ""
        if name:
            names.append(name)
    return names


def assemble_llm_messages(
    ctx: Any,
    *,
    manifest: dict | None = None,
    correlation_id: int = 0,
    tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build OpenAI-shaped messages via the registered assembler plugin."""
    plugin = cached_assembler(ctx, manifest)
    assemble = getattr(plugin, "assemble_messages", None)
    if not callable(assemble):
        raise TypeError(
            f"{type(plugin).__name__} is not a context assembler "
            "(missing assemble_messages)"
        )
    messages = assemble(
        ctx,
        manifest=manifest,
        correlation_id=correlation_id,
        tools=tools,
    )
    assert_provider_payload(messages)

    obs = getattr(ctx, "observability", None)
    cid = correlation_id or int(getattr(ctx, "_assembly_correlation_id", 0) or 0)
    record_context_assembly(
        obs,
        correlation_id=cid,
        messages=messages,
        turn_index=int(getattr(ctx, "turn_index", 0) or 0),
        agent_id=str(getattr(ctx, "agent_id", "agent") or "agent"),
        tools=_openai_tool_names(tools),
    )
    return messages


def compact_committed_history(ctx: Any, *, manifest: dict | None = None) -> None:
    """Ask the assembler plugin to rewrite stored history to its recency cap."""
    resolved = manifest if manifest is not None else getattr(ctx, "manifest", None)
    plugin = cached_assembler(ctx, resolved)
    compact = getattr(plugin, "compact_committed_history", None)
    if not callable(compact):
        return
    compact(ctx, manifest=resolved)


def llm_request_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    _ = messages
    return tools or None


def llm_tool_choice(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
) -> str | None:
    _ = messages
    return "auto" if tools else None


def has_tool_results(messages: list[dict[str, Any]]) -> bool:
    return any(m.get("role") == "tool" for m in messages)


__all__ = [
    "assemble_llm_messages",
    "compact_committed_history",
    "has_tool_results",
    "llm_request_tools",
    "llm_tool_choice",
]
