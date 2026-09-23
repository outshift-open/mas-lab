#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Conversation-history strategies — ContextManagerContract plugins.

SOTA recency: keep the last N **user turns** verbatim (user + everything until
the next user, including tool ask/result groups). Older history is dropped
(sliding-window / stack) or compressed into one summary block (summarising).
The live tool round lives in working memory and is not passed here.

Pairing repair itself runs once later, in ``assemble_llm_messages``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from mas.runtime.boundary.context.provider_invariant import split_user_turns, start_of_tool_group
from mas.runtime.contracts.context_manager_contract import ContextManagerContract

_log = logging.getLogger(__name__)

# Matches spec.context_manager.params.keep_turns / hysteresis_ratio schema defaults.
_DEFAULT_KEEP_TURNS = 10
_DEFAULT_HYSTERESIS_RATIO = 0.2


def _flatten(turns: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [msg for turn in turns for msg in turn]


class StackConversation(ContextManagerContract):
    """Keep full history, optionally capped to last ``max_messages`` messages.

    If the cut would land on a tool result, the slice starts at that result's
    assistant instead, so the ask and answers stay together.
    """

    def __init__(self, max_messages: int | None = None) -> None:
        if max_messages is not None and max_messages < 1:
            raise ValueError(f"max_messages must be >= 1, got {max_messages}")
        self.max_messages = max_messages

    def manage_history(
        self,
        past: list[dict[str, Any]],
        budget_tokens: int,
    ) -> list[dict[str, Any]]:
        _ = budget_tokens
        if not past or self.max_messages is None or len(past) <= self.max_messages:
            return list(past)
        start = start_of_tool_group(past, len(past) - self.max_messages)
        evicted = start
        if evicted:
            _log.debug(
                "StackConversation: evicted %d message(s), keeping last %d (tool-group aligned)",
                evicted,
                len(past) - start,
            )
        return list(past[start:])


class SlidingWindowConversation(ContextManagerContract):
    """Keep the last ``keep_turns`` user turns verbatim; drop older turns."""

    def __init__(
        self,
        max_turns: int = _DEFAULT_KEEP_TURNS,
        window_size: int | None = None,
        keep_turns: int | None = None,
    ) -> None:
        if keep_turns is not None:
            max_turns = int(keep_turns)
        elif window_size is not None:
            max_turns = int(window_size)
        self.max_turns = max(1, int(max_turns))
        self.keep_turns = self.max_turns

    def manage_history(
        self,
        past: list[dict[str, Any]],
        budget_tokens: int,
    ) -> list[dict[str, Any]]:
        _ = budget_tokens
        if not past:
            return []
        turns = split_user_turns(past)
        if len(turns) <= self.max_turns:
            return list(past)
        kept = turns[-self.max_turns :]
        _log.debug(
            "SlidingWindowConversation: evicted %d turn(s), keeping last %d",
            len(turns) - self.max_turns,
            self.max_turns,
        )
        return _flatten(kept)


class SummarizingConversation(ContextManagerContract):
    """Keep recent user turns verbatim; summarize only older history.

    Compaction is a *view* over the still-growing committed history, so the
    same older turns would otherwise be re-summarized on every LLM call.
    After a compaction, the cached summary is reused while new turns append
    verbatim, until the managed payload exceeds ``budget * (1 + hysteresis_ratio)``.
    """

    def __init__(
        self,
        summary_threshold: int = 0,
        keep_turns: int = _DEFAULT_KEEP_TURNS,
        hysteresis_ratio: float = _DEFAULT_HYSTERESIS_RATIO,
        summarize_fn: Callable[[list[dict[str, Any]]], str] | None = None,
    ) -> None:
        self.summary_threshold = max(0, int(summary_threshold))
        self.keep_turns = max(1, int(keep_turns))
        self.hysteresis_ratio = min(1.0, max(0.0, float(hysteresis_ratio)))
        self._summarize_fn = summarize_fn
        self.last_compaction_metadata: dict[str, Any] | None = None
        self._cached_summary: str | None = None
        self._cached_n_compressed: int = 0

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        total = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total += len(content)
        return total // 4 + len(messages) * 4

    def _clear_cache(self) -> None:
        self._cached_summary = None
        self._cached_n_compressed = 0

    def _budget(self, budget_tokens: int) -> int:
        return budget_tokens if budget_tokens > 0 else self.summary_threshold

    def _retrigger_ceiling(self, high: int) -> int:
        return max(high, int(high * (1.0 + self.hysteresis_ratio)))

    def _summary_block(self, n_compressed: int, text: str) -> dict[str, Any]:
        return {
            "role": "system",
            "content": (
                f"[Conversation summary — {n_compressed} earlier exchange(s)]\n"
                f"{text}"
            ),
        }

    def _cached_view(self, turns: list[list[dict[str, Any]]]) -> list[dict[str, Any]] | None:
        n = self._cached_n_compressed
        if n <= 0 or n >= len(turns):
            return None
        suffix = _flatten(turns[n:])
        if self._cached_summary is None:
            return suffix
        return [self._summary_block(n, self._cached_summary)] + suffix

    def manage_history(
        self,
        past: list[dict[str, Any]],
        budget_tokens: int,
    ) -> list[dict[str, Any]]:
        if not past:
            self._clear_cache()
            return []

        high = self._budget(budget_tokens)
        raw_tokens = self._estimate_tokens(past)
        if high <= 0 or raw_tokens <= high:
            self._clear_cache()
            return list(past)

        turns = split_user_turns(past)
        keep = self.keep_turns
        if self._cached_n_compressed >= len(turns):
            self._clear_cache()

        cached = self._cached_view(turns)
        if cached is not None:
            managed_tokens = self._estimate_tokens(cached)
            if managed_tokens <= self._retrigger_ceiling(high):
                self.last_compaction_metadata = {
                    "reused": True,
                    "compressed_exchanges": self._cached_n_compressed,
                    "kept_exchanges": len(turns) - self._cached_n_compressed,
                }
                return cached

        if len(turns) <= keep:
            return list(past)

        to_compress = turns[:-keep]
        verbatim = turns[-keep:]
        to_compress_msgs = _flatten(to_compress)
        verbatim_msgs = _flatten(verbatim)
        n_compressed = len(to_compress)

        if self._summarize_fn is None:
            self._cached_summary = None
            self._cached_n_compressed = n_compressed
            self.last_compaction_metadata = {
                "compressed_exchanges": 0,
                "dropped_exchanges": n_compressed,
                "kept_exchanges": len(verbatim),
            }
            _log.debug(
                "SummarizingConversation: no summarize_fn; dropped %d older turn(s), keeping last %d",
                n_compressed,
                keep,
            )
            return verbatim_msgs

        try:
            summary_text = self._summarize_fn(to_compress_msgs)
        except Exception as exc:
            _log.warning(
                "SummarizingConversation: summarize_fn failed (%s); keeping last %d turn(s) verbatim",
                exc,
                keep,
            )
            return verbatim_msgs

        self._cached_summary = summary_text
        self._cached_n_compressed = n_compressed
        self.last_compaction_metadata = {
            "compressed_exchanges": n_compressed,
            "kept_exchanges": len(verbatim),
            "reused": False,
        }
        return [self._summary_block(n_compressed, summary_text)] + verbatim_msgs
