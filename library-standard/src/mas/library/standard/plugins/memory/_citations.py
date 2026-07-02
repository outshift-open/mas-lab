# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Citations formatter — orthogonal presentation axis.

Controls how memory search results are formatted before injection
into context or tool responses.

Tagged implementations:
- ``NoCitationsFormatter``   — strip source info (mode="off")
- ``FullCitationsFormatter``  — always include source (mode="on")
- ``AutoCitationsFormatter``  — include when useful (mode="auto", default)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default citation mode
DEFAULT_CITATIONS_MODE = "auto"
DEFAULT_MAX_SNIPPET_CHARS = 700


class CitationFormatter(ABC):
    """Abstract citation formatter for memory search results."""

    version: str = "abstract"

    @abstractmethod
    def format_result(self, result: Dict[str, Any]) -> str:
        """Format a single search result with/without citation."""
        ...

    @abstractmethod
    def format_results(self, results: List[Dict[str, Any]]) -> str:
        """Format a list of search results."""
        ...


class NoCitationsFormatter(CitationFormatter):
    """Strip source information from results (mode='off')."""

    version = "citations-off-v1"

    def __init__(self, max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS) -> None:
        self._max_chars = max_snippet_chars

    def format_result(self, result: Dict[str, Any]) -> str:
        text = result.get("text", "")
        return text[:self._max_chars]

    def format_results(self, results: List[Dict[str, Any]]) -> str:
        lines = [f"- {self.format_result(r)}" for r in results]
        return "\n".join(lines)


class FullCitationsFormatter(CitationFormatter):
    """Always include source citations (mode='on').

    Format: ``text ... (Source: path#line)``
    """

    version = "citations-on-v1"

    def __init__(self, max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS) -> None:
        self._max_chars = max_snippet_chars

    def format_result(self, result: Dict[str, Any]) -> str:
        text = result.get("text", "")[:self._max_chars]
        source = result.get("source", "")
        score = result.get("score", 0.0)
        chunk = result.get("chunk", {})

        citation = source
        if chunk.get("char_start") is not None:
            citation = f"{source}#char{chunk['char_start']}"

        return f"{text}\n  Source: {citation} (score: {score:.2f})"

    def format_results(self, results: List[Dict[str, Any]]) -> str:
        lines = [f"- {self.format_result(r)}" for r in results]
        return "\n".join(lines)


class AutoCitationsFormatter(CitationFormatter):
    """Include citations when useful (mode='auto', the default).

    Includes source when score is above threshold or when multiple
    sources are present, omits for single high-confidence matches.
    """

    version = "citations-auto-v1"

    def __init__(
        self,
        max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS,
        cite_threshold: float = 0.5,
    ) -> None:
        self._max_chars = max_snippet_chars
        self._cite_threshold = cite_threshold

    def format_result(
        self, result: Dict[str, Any], force_cite: bool = False
    ) -> str:
        text = result.get("text", "")[:self._max_chars]
        source = result.get("source", "")
        score = result.get("score", 0.0)

        if force_cite or score >= self._cite_threshold:
            return f"{text}\n  Source: {source} (score: {score:.2f})"
        return text

    def format_results(self, results: List[Dict[str, Any]]) -> str:
        # Show citations if multiple distinct sources
        sources = {r.get("source", "") for r in results}
        force = len(sources) > 1

        lines = [f"- {self.format_result(r, force_cite=force)}" for r in results]
        return "\n".join(lines)


def create_citation_formatter(
    mode: str = DEFAULT_CITATIONS_MODE,
    max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS,
) -> CitationFormatter:
    """Factory: create a CitationFormatter from a mode string."""
    if mode == "off":
        return NoCitationsFormatter(max_snippet_chars=max_snippet_chars)
    elif mode == "on":
        return FullCitationsFormatter(max_snippet_chars=max_snippet_chars)
    else:  # "auto"
        return AutoCitationsFormatter(max_snippet_chars=max_snippet_chars)
