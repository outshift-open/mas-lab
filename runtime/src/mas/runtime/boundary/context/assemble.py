#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Assemble LLM ``messages[]`` for kernel engines — CMFactory + working memory.

Message layers (in order appended to the provider payload):

1. **System** — injected context, memory seeds, context plugins.
2. **Committed history** — chunk store / ``committed_messages`` / turn history,
   then passed through ``CMFactory`` (registry ``context_manager`` plugin;
   defaults to ``defaults.yaml`` when ``spec.context_manager`` is omitted).
   Context-manager plugins must return provider-safe history themselves.
3. **Current user** — ``last_user_text`` for this ingress.
4. **In-turn working memory (WM)** — assistant/tool messages from the current
   dispatch loop, read from ``ctx.working_memory`` (``WorkingMemoryStore``).

Optional trim: set ``spec.context_manager.params.trimmer`` with ``max_tokens``
(and optional ``reserve_tokens``). When ``trimmer`` is absent, WM is appended
with no token-based trimming. WM is passed as ``pin_tail`` only when trim runs.
"""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.context.assembly_cache import cached_context_manager
from mas.runtime.boundary.context.assembly_trim import (
    assembly_trimmer_params,
    context_manager_history_budget_hint,
    trim_assembled_messages,
)
from mas.runtime.boundary.context.conversation_chunks import ConversationChunkStore
from mas.runtime.boundary.context.working_memory import (
    WorkingMemoryStore,
    bounded_working_memory_tail,
    working_memory_slice_limit,
)


def _turn_history_to_past(turn_history: list[tuple[str, str]]) -> list[dict[str, Any]]:
    past: list[dict[str, Any]] = []
    for user_q, assistant_a in turn_history:
        past.append({"role": "user", "content": user_q})
        if assistant_a.strip():
            past.append({"role": "assistant", "content": assistant_a})
    return past


def _pinned_working_memory(ctx: Any, manifest: dict | None = None) -> list[dict[str, Any]]:
    store = getattr(ctx, "working_memory", None)
    if isinstance(store, WorkingMemoryStore) and store.messages:
        return bounded_working_memory_tail(store.messages, working_memory_slice_limit(manifest))
    return []


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
    """Build OpenAI-shaped messages: system → committed history → user → WM / trim."""
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

    cm = cached_context_manager(ctx, manifest)
    managed = cm.manage_history(past, context_manager_history_budget_hint(manifest))
    messages.extend(managed)

    last_user_text = str(getattr(ctx, "last_user_text", "") or "")
    if last_user_text:
        messages.append({"role": "user", "content": last_user_text})

    wm_messages = _pinned_working_memory(ctx, manifest)

    if not messages and not wm_messages:
        messages.append({"role": "user", "content": "Hello"})

    trimmer = assembly_trimmer_params(manifest)
    if trimmer is not None:
        max_tokens, reserve = trimmer
        messages = trim_assembled_messages(
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
        tools=_openai_tool_names(tools),
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
