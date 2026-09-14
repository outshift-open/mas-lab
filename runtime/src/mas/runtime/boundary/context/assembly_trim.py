#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Optional assembly token trim — enabled by ``spec.context_manager.params.trimmer``."""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.context.trim import context_manager_spec
from mas.runtime.spec.defaults import DEFAULT_CONTEXT_RESERVE_TOKENS


def assembly_trimmer_params(manifest: dict | None) -> tuple[int, int] | None:
    """Return ``(max_tokens, reserve_tokens)`` when trimmer params are configured."""
    cm = context_manager_spec(manifest)
    params = cm.get("params") or {}
    trimmer = params.get("trimmer")
    if not isinstance(trimmer, dict) or not trimmer:
        return None
    raw_max = trimmer.get("max_tokens") or trimmer.get("token_budget")
    if raw_max is None:
        return None
    try:
        max_tokens = int(raw_max)
        reserve = int(trimmer.get("reserve_tokens", DEFAULT_CONTEXT_RESERVE_TOKENS))
    except (TypeError, ValueError):
        return None
    if max_tokens < 1:
        return None
    return max_tokens, max(0, reserve)


def context_manager_history_budget_hint(manifest: dict | None) -> int:
    """Token hint for ``manage_history`` (e.g. summarising CM); 0 when trimmer off."""
    params = assembly_trimmer_params(manifest)
    return params[0] if params else 0


def trim_assembled_messages(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    reserve_tokens: int,
    pin_tail: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Standard tool-group-aware trim (implementation in mas-library-standard)."""
    from mas.library.standard.plugins.context.token_budget import trim_messages_to_budget

    return trim_messages_to_budget(
        messages,
        max_tokens=max_tokens,
        reserve_tokens=reserve_tokens,
        pin_tail=pin_tail,
    )
