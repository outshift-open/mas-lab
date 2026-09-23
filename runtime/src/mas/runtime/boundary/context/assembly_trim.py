#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Assembly token trim — budget from ``params.trimmer`` or the model context window."""

from __future__ import annotations

from typing import Any

from mas.runtime.spec.history_budget import derived_trimmer_params, history_token_budget


def assembly_trimmer_params(manifest: dict | None) -> tuple[int, int] | None:
    """Return ``(max_tokens, reserve_tokens)`` for the assembled payload cap.

    Uses explicit ``spec.context_manager.params.trimmer`` when set; otherwise
    the primary model's ``context_window`` minus completion ``max_tokens``.
    """
    max_tokens, reserve = derived_trimmer_params(manifest)
    if max_tokens < 1:
        return None
    return max_tokens, max(0, reserve)


def context_manager_history_budget_hint(manifest: dict | None) -> int:
    """Token hint for ``manage_history``: context window minus completion reserve."""
    return history_token_budget(manifest)


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
