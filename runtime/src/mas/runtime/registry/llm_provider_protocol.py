#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Protocol for pluggable LLM wire-protocol providers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM-provider plugins in the MAS runtime.

    Runtime calling is a chat-completion. A plugin speaks one wire protocol
    (OpenAI-compatible HTTP, later Bedrock, …). Cache is a wrapper around a
    routed protocol plugin, not a protocol. Offline CI replays a recorded
    live provider through ``llm_cache`` (``raise_on_miss``).
    The engine assembles messages and parses the returned OpenAI-shaped
    assistant message; it does not own vendor HTTP.
    """

    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return an OpenAI-shaped assistant ``message`` dict.

        Optional kwargs:
        **static (also on spec.models[])** — ``reasoning`` / ``reasoning_effort``,
        ``sampling``, ``extra_body``.
        **dynamic (per call)** — ``stream``, ``stream_options``, ``on_stream_chunk``,
        ``api_key``, ``tool_choice``, ``extra_headers``, ``extra_query``.
        """
        ...
