#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Rewrite stored committed history to the context manager's recency cap."""

from __future__ import annotations

from typing import Any

from mas.library.standard.lib.context.payload import split_user_turns
from mas.runtime.boundary.context.assembly_cache import cached_context_manager
from mas.runtime.boundary.context.conversation_chunks import ConversationChunkStore


def _storage_turn_cap(cm: Any) -> int | None:
    for attr in ("keep_turns", "max_turns"):
        raw = getattr(cm, attr, None)
        if raw is not None:
            try:
                cap = int(raw)
            except (TypeError, ValueError):
                continue
            if cap >= 1:
                return cap
    return None


def _storage_message_cap(cm: Any) -> int | None:
    raw = getattr(cm, "max_messages", None)
    if raw is None:
        return None
    try:
        cap = int(raw)
    except (TypeError, ValueError):
        return None
    return cap if cap >= 1 else None


def compact_committed_history(ctx: Any, *, manifest: dict | None = None) -> None:
    """Rewrite ``ctx`` committed history to the context manager's bounded view."""
    store = getattr(ctx, "conversation_chunks", None)
    committed = list(getattr(ctx, "committed_messages", []) or [])
    if isinstance(store, ConversationChunkStore) and (store.order or store.summary_chunk_id):
        past = store.project_messages()
    else:
        past = committed
    if not past:
        return

    resolved = manifest if manifest is not None else getattr(ctx, "manifest", None)
    cm = cached_context_manager(ctx, resolved)
    turn_cap = _storage_turn_cap(cm)
    n_turns = len(split_user_turns(past))
    over_turns = turn_cap is not None and n_turns > turn_cap
    msg_cap = _storage_message_cap(cm)
    over_msgs = msg_cap is not None and len(past) > msg_cap
    if not over_turns and not over_msgs:
        return
    managed = cm.manage_history(past, 1)
    if managed == past:
        return

    if isinstance(getattr(ctx, "committed_messages", None), list):
        ctx.committed_messages[:] = list(managed)
    else:
        ctx.committed_messages = list(managed)

    history = getattr(ctx, "turn_history", None)
    if isinstance(history, list):
        n_managed_turns = len(split_user_turns(managed))
        if n_managed_turns == 0:
            ctx.turn_history = []
        elif len(history) > n_managed_turns:
            ctx.turn_history = history[-n_managed_turns:]

    if isinstance(store, ConversationChunkStore):
        store.replace_with(split_user_turns(managed))
