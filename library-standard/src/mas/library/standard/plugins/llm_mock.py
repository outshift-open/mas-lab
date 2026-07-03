#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-process mock model access — cache lookup with schema-driven tool-call fallback."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from mas.runtime.boundary.context.assemble import has_tool_results
from mas.runtime.engine.llm_cache import (
    assistant_message_from_cache_content,
    last_user_text,
    load_cache,
    lookup_response,
    resolve_cache_path,
)

from mas.library.standard.mock_llm import openai_tools_to_specs, pick_tool_call


class MockModelAccess:
    """Offline model access for CI and tutorials (no HTTP, no API key)."""

    provider_id = "mock"

    def __init__(self, cache_path: str | Path | None = None, **_: Any) -> None:
        self._cache_path = resolve_cache_path(cache_path)
        self._cache = load_cache(self._cache_path)

    @property
    def available(self) -> bool:
        return True

    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """Return an OpenAI-shaped assistant ``message`` dict."""
        _ = temperature, max_tokens
        content, _usage, _source = lookup_response(
            self._cache, model, messages, tools=tools
        )
        cached = assistant_message_from_cache_content(content)
        if cached is not None:
            return cached

        if has_tool_results(messages):
            tool_text = "\n".join(
                str(m.get("content") or "")
                for m in messages
                if m.get("role") == "tool"
            ).strip()
            if tool_text:
                return {"role": "assistant", "content": tool_text[:2000]}

        user = last_user_text(messages)
        if tools and not has_tool_results(messages):
            picked = pick_tool_call(user, openai_tools_to_specs(tools))
            if picked is not None:
                name, args = picked
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args),
                            },
                        }
                    ],
                }

        if user.strip():
            return {
                "role": "assistant",
                "content": f"[mock] {user.strip()[:500]}",
            }
        return {"role": "assistant", "content": "[mock] ready"}
