#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Assemble LLM ``messages[]`` for kernel engines — CMFactory + working memory."""

from __future__ import annotations

from typing import Any

from mas.library.standard.plugins.context.provider_payload import sanitize_provider_messages
from mas.runtime.boundary.context.conversation_chunks import ConversationChunkStore
from mas.runtime.boundary.context.trim import context_manager_spec
from mas.runtime.boundary.context.working_memory import WorkingMemoryStore
from mas.runtime.contracts.cm_factory import CMFactory


def _turn_history_to_past(turn_history: list[tuple[str, str]]) -> list[dict[str, Any]]:
    past: list[dict[str, Any]] = []
    for user_q, assistant_a in turn_history:
        past.append({"role": "user", "content": user_q})
        if assistant_a.strip():
            past.append({"role": "assistant", "content": assistant_a})
    return past


def _token_budget_params(manifest: dict | None) -> tuple[int | None, int]:
    cm = context_manager_spec(manifest)
    params = cm.get("params") or {}
    raw_max = params.get("token_budget") or params.get("max_tokens")
    if raw_max is None:
        return None, 512
    try:
        return int(raw_max), int(params.get("reserve_tokens", 512))
    except (TypeError, ValueError):
        return None, 512


def _pinned_working_memory(ctx: Any) -> list[dict[str, Any]]:
    """In-turn working memory is structurally pinned from budget trimming.

    Each session/ctx carries its own ``WorkingMemoryStore``; assembly never
    reads global kernel state for message content.
    """
    store = getattr(ctx, "working_memory", None)
    if isinstance(store, WorkingMemoryStore) and store.messages:
        return list(store.messages)
    return []


def assemble_llm_messages(
    ctx: Any,
    *,
    manifest: dict | None = None,
    correlation_id: int = 0,
) -> list[dict[str, Any]]:
    """Build OpenAI-shaped messages: system → committed history → user → pinned WM."""
    messages: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for line in getattr(ctx, "injected_context", []) or []:
        if str(line).strip():
            system_parts.append(str(line).strip())
    for key, content in getattr(ctx, "memory_seeds", []) or []:
        system_parts.append(f"[memory:{key}] {content}")
    _inject_context_plugins(ctx, system_parts)
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    chunk_store = getattr(ctx, "conversation_chunks", None)
    committed = list(getattr(ctx, "committed_messages", []) or [])
    if isinstance(chunk_store, ConversationChunkStore) and (
        chunk_store.order or chunk_store.summary_chunk_id
    ):
        past = chunk_store.project_messages()
    elif committed:
        past = list(committed)
    else:
        past = _turn_history_to_past(list(getattr(ctx, "turn_history", []) or []))
    managed = CMFactory.create(manifest=manifest).manage_history(past, _token_budget_params(manifest)[0] or 0)
    messages.extend(managed)

    last_user_text = str(getattr(ctx, "last_user_text", "") or "")
    if last_user_text:
        messages.append({"role": "user", "content": last_user_text})

    wm_messages = _pinned_working_memory(ctx)

    if not messages and not wm_messages:
        messages.append({"role": "user", "content": "Hello"})

    messages = sanitize_provider_messages(messages)
    max_tokens, reserve = _token_budget_params(manifest)
    if max_tokens is not None:
        from mas.library.standard.plugins.context.token_budget import trim_messages_to_budget

        messages = trim_messages_to_budget(
            messages,
            max_tokens=max_tokens,
            reserve_tokens=reserve,
            pin_tail=wm_messages,
        )
    else:
        messages = messages + wm_messages

    from mas.runtime.boundary.context.telemetry import record_context_assembly

    obs = getattr(ctx, "observability", None)
    cid = correlation_id or int(getattr(ctx, "_assembly_correlation_id", 0) or 0)
    record_context_assembly(
        obs,
        correlation_id=cid,
        messages=messages,
        turn_index=int(getattr(ctx, "turn_index", 0) or 0),
        agent_id=str(getattr(ctx, "agent_id", "agent") or "agent"),
    )
    return messages


def _inject_context_plugins(ctx: Any, system_parts: list[str]) -> None:
    collection = getattr(ctx, "plugin_collection", None)
    if not collection:
        return

    from mas.runtime.contracts.context_contract import (
        _SYSTEM_PLACEMENTS_ORDER,
        ContextPart,
        ContextPlacement,
    )

    raw_parts = collection.collect_results("collect_context")
    if not raw_parts:
        return

    placement_order = {pl: i for i, pl in enumerate(_SYSTEM_PLACEMENTS_ORDER)}

    def _sort_key(part: Any) -> tuple[int, int]:
        placement = getattr(part, "placement", ContextPlacement.SYSTEM_BODY)
        priority = getattr(part, "priority", 60)
        return (placement_order.get(placement, 99), priority)

    for part in sorted(
        (p for p in raw_parts if isinstance(p, ContextPart)),
        key=_sort_key,
    ):
        if str(part.content).strip():
            system_parts.append(str(part.content).strip())


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
    "has_tool_results",
    "llm_request_tools",
    "llm_tool_choice",
]
