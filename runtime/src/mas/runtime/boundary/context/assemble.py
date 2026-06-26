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


def llm_request_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Tools for the API payload — omitted on answer-from-tool-result turns."""
    if not tools:
        return None
    if _has_tool_results(messages):
        return None
    return tools


def llm_tool_choice(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
) -> str | None:
    """OpenAI tool_choice when tools are included."""
    if not tools or _has_tool_results(messages):
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
