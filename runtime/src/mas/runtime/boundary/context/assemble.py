#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Assemble LLM ``messages[]`` for kernel engines — CMFactory + working memory."""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.context.trim import context_manager_spec
from mas.runtime.boundary.context.working_memory import (
    WorkingMemoryStore,
    working_memory_source,
)
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


def _apply_token_budget(
    messages: list[dict[str, Any]],
    manifest: dict | None,
) -> list[dict[str, Any]]:
    max_tokens, reserve = _token_budget_params(manifest)
    if max_tokens is None:
        return messages
    from mas.library.standard.plugins.context.token_budget import trim_messages_to_budget

    return trim_messages_to_budget(
        messages, max_tokens=max_tokens, reserve_tokens=reserve
    )


def assemble_llm_messages(
    ctx: Any,
    *,
    manifest: dict | None = None,
    correlation_id: int = 0,
) -> list[dict[str, Any]]:
    """Build OpenAI-shaped messages: system → committed history → user → in-turn working memory."""
    store = getattr(ctx, "working_memory", None) or WorkingMemoryStore()
    wm = working_memory_source(store)

    messages: list[dict[str, Any]] = []
    system_parts: list[str] = []
    for line in getattr(ctx, "injected_context", []) or []:
        if str(line).strip():
            system_parts.append(str(line).strip())
    for key, content in getattr(ctx, "memory_seeds", []) or []:
        system_parts.append(f"[memory:{key}] {content}")
    # ctx_collect_execute — v0.1 wiring: call collect_context() on all registered
    # ContextContract plugins via plugin_collection.collect_results().
    # This uses the same interface that ContextAssemblerPlugin.on_pre_llm_call()
    # expects as agent.registry — so when the full assembler is wired into the
    # kernel this bridge can be removed without changing plugin behavior.
    _inject_context_plugins(ctx, system_parts)
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    committed = list(getattr(ctx, "committed_messages", []) or [])
    if committed:
        past = list(committed)
    else:
        turn_history = list(getattr(ctx, "turn_history", []) or [])
        past = _turn_history_to_past(turn_history)
    cm = CMFactory.create(manifest=manifest)
    max_tokens, _ = _token_budget_params(manifest)
    managed = cm.manage_history(past, max_tokens or 0)
    messages.extend(managed)

    last_user_text = str(getattr(ctx, "last_user_text", "") or "")
    if last_user_text:
        messages.append({"role": "user", "content": last_user_text})

    messages.extend(wm.collect_context(manifest=manifest))

    if not messages:
        messages.append({"role": "user", "content": "Hello"})
    messages = _apply_token_budget(messages, manifest)

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


def _has_tool_results(messages: list[dict[str, Any]]) -> bool:
    return any(m.get("role") == "tool" for m in messages)


def _inject_context_plugins(ctx: Any, system_parts: list[str]) -> None:
    """Dispatch ctx_collect_execute to registered ContextContract plugins.

    Calls ``plugin_collection.collect_results("collect_context")`` on the
    context object's ``plugin_collection`` (a ``PluginCollection`` instance).
    Gathered ``ContextPart`` objects are sorted by placement order + priority
    before their content is appended to *system_parts*.

    This is the v0.1 bridge for the ctx_collect_execute FSM symbol.  It uses
    the same ``collect_results()`` interface that ``ContextAssemblerPlugin``
    expects as ``agent.registry``, so the bridge can be removed once the full
    assembler plugin is wired into the kernel without any change to plugins.
    """
    collection = getattr(ctx, "plugin_collection", None)
    if not collection:
        return

    from mas.runtime.contracts.context_contract import (
        ContextPart,
        ContextPlacement,
        _SYSTEM_PLACEMENTS_ORDER,
    )

    raw_parts = collection.collect_results("collect_context")
    if not raw_parts:
        return

    # Sort by placement band then priority, matching ContextAssemblerPlugin order.
    placement_order = {pl: i for i, pl in enumerate(_SYSTEM_PLACEMENTS_ORDER)}

    def _sort_key(part: Any) -> tuple[int, int]:
        placement = getattr(part, "placement", ContextPlacement.SYSTEM_BODY)
        priority = getattr(part, "priority", 60)
        return (placement_order.get(placement, 99), priority)

    sorted_parts = sorted(
        (p for p in raw_parts if isinstance(p, ContextPart)),
        key=_sort_key,
    )

    for part in sorted_parts:
        if str(part.content).strip():
            system_parts.append(str(part.content).strip())


def llm_request_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Tools for the API payload.

    Tools stay available after tool results so ReAct loops can issue further
    ``tool_calls`` (e.g. chained ``delegate_to_*``).

    ``messages`` is retained for call-site compatibility and future guards
    (e.g. post-tool synthesis); it is not read in the current ReAct-only path.
    """
    _ = messages
    if not tools:
        return None
    return tools


def llm_tool_choice(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
) -> str | None:
    """OpenAI tool_choice when tools are included.

    ``messages`` is retained for call-site compatibility; not read currently.
    """
    _ = messages
    if not tools:
        return None
    return "auto"


__all__ = [
    "assemble_llm_messages",
    "has_tool_results",
    "llm_request_tools",
    "llm_tool_choice",
]


def has_tool_results(messages: list[dict[str, Any]]) -> bool:
    return _has_tool_results(messages)
