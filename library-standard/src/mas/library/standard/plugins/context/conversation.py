#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Conversation-history strategies — ContextManagerContract plugins."""

from __future__ import annotations

import logging
from typing import Any, Callable

from mas.library.standard.plugins.context.tool_pairing import group_exchanges, skip_tool_group
from mas.runtime.contracts.context_manager_contract import ContextManagerContract

_log = logging.getLogger(__name__)


class StackConversation(ContextManagerContract):
    """Keep full history, optionally capped to last ``max_messages`` messages."""

    def __init__(self, max_messages: int | None = None) -> None:
        if max_messages is not None and max_messages < 1:
            raise ValueError(f"max_messages must be >= 1, got {max_messages}")
        self.max_messages = max_messages

    def manage_history(
        self,
        past: list[dict[str, Any]],
        budget_tokens: int,
    ) -> list[dict[str, Any]]:
        if not past or self.max_messages is None:
            return past
        if len(past) <= self.max_messages:
            return past

        tail = list(past)
        while len(tail) > self.max_messages:
            n = skip_tool_group(tail, 0)
            if n >= len(tail):
                break
            del tail[:n]

        _log.debug(
            "StackConversation: evicted %d message(s), keeping last %d",
            len(past) - len(tail),
            len(tail),
        )
        return tail


class SlidingWindowConversation(ContextManagerContract):
    """Keep the last ``max_turns`` user/assistant exchange pairs."""

    def __init__(self, max_turns: int = 20, window_size: int | None = None) -> None:
        if window_size is not None:
            max_turns = int(window_size)
        self.max_turns = max(1, int(max_turns))

    def manage_history(
        self,
        past: list[dict[str, Any]],
        budget_tokens: int,
    ) -> list[dict[str, Any]]:
        if not past:
            return past

        exchanges = group_exchanges(past)

        if len(exchanges) <= self.max_turns:
            return past

        kept = exchanges[-self.max_turns :]
        evicted = len(exchanges) - self.max_turns
        _log.debug(
            "SlidingWindowConversation: evicted %d exchange(s), keeping last %d",
            evicted,
            self.max_turns,
        )
        return [msg for exchange in kept for msg in exchange]


class SummarizingConversation(ContextManagerContract):
    """Compress older turns into a summary system block (LangGraph-style)."""

    def __init__(
        self,
        summary_threshold: int = 4000,
        keep_turns: int = 10,
        summarize_fn: Callable[[list[dict[str, Any]]], str] | None = None,
    ) -> None:
        if summarize_fn is None:
            raise ValueError(
                "SummarizingConversation requires summarize_fn; "
                "register an LLM-backed summarizer via manifest params or plugin wiring"
            )
        self.summary_threshold = summary_threshold
        self.keep_turns = keep_turns
        self._summarize_fn = summarize_fn
        self.last_compaction_metadata: dict[str, Any] | None = None

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        total = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total += len(content)
        return total // 4 + len(messages) * 4

    def manage_history(
        self,
        past: list[dict[str, Any]],
        budget_tokens: int,
    ) -> list[dict[str, Any]]:
        if not past:
            return past

        effective = budget_tokens if budget_tokens else self.summary_threshold
        if self._estimate_tokens(past) <= effective:
            return past

        exchanges = group_exchanges(past)

        if len(exchanges) <= self.keep_turns:
            return past

        to_compress = exchanges[: -self.keep_turns]
        verbatim = exchanges[-self.keep_turns :]
        to_compress_msgs = [msg for ex in to_compress for msg in ex]

        if self._summarize_fn is not None:
            try:
                summary_text = self._summarize_fn(to_compress_msgs)
            except Exception as exc:  # pragma: no cover
                _log.warning("SummarizingConversation: summarize_fn failed (%s)", exc)
                raise
        else:
            raise RuntimeError("SummarizingConversation: summarize_fn is required")

        self.last_compaction_metadata = {
            "compressed_exchanges": len(to_compress),
            "kept_exchanges": len(verbatim),
        }
        summary_block = {
            "role": "system",
            "content": (
                f"[Conversation summary — {len(to_compress)} earlier exchange(s)]\n"
                f"{summary_text}"
            ),
        }
        return [summary_block] + [msg for ex in verbatim for msg in ex]
