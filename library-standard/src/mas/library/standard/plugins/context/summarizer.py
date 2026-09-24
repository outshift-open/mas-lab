#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Summarizer sub-plugins for ``SummarizingConversation``.

Registry type ``summarizer``. Bound by ``CMFactory`` onto a summarising
context manager — not a standalone spec slot.

- ``llm`` (default): this agent's engine (``summarize_messages``).
- ``drop``: discard older turns; keep ``keep_turns`` verbatim.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)

SUMMARIZE_INSTRUCTIONS = (
    "Summarize the following conversation turns concisely, preserving key "
    "facts, decisions, and any identifiers (names, IDs, numbers) a later "
    "turn might need to reference. Write plain prose, not a transcript."
)


class DropSummarizer:
    """Discard older turns. The context manager keeps ``keep_turns`` verbatim."""

    def summarize(self, messages: list[dict[str, Any]]) -> str | None:
        _ = messages
        return None


class LlmSummarizer:
    """Summarize older turns with the agent's live engine.

    ``bind_engine`` is called by ``CMFactory`` after construction — the engine
    is a runtime object, not a spec param. Without a ``summarize_messages``
    engine this degrades to drop and logs a warning.
    """

    def __init__(self) -> None:
        self._engine: Any | None = None
        self._warned_no_engine = False

    def bind_engine(self, engine: Any | None) -> None:
        self._engine = engine

    def summarize(self, messages: list[dict[str, Any]]) -> str | None:
        engine = self._engine
        fn = getattr(engine, "summarize_messages", None) if engine is not None else None
        if not callable(fn):
            if not self._warned_no_engine:
                _log.warning(
                    "summarizer llm has no engine.summarize_messages; "
                    "older turns will be dropped. Bind the agent engine or set summarizer: drop."
                )
                self._warned_no_engine = True
            return None
        text = fn(
            [
                {"role": "system", "content": SUMMARIZE_INSTRUCTIONS},
                {"role": "user", "content": json.dumps(messages, default=str)},
            ]
        )
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        return stripped or None
