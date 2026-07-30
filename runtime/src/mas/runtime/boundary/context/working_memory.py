#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Working memory — L1 in-turn trajectory (``source_type=working_memory`` context source)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mas.runtime.boundary.context.trim import context_manager_spec

SOURCE_TYPE = "working_memory"


def _slice_limit(manifest: dict | None) -> int:
    cm = context_manager_spec(manifest)
    params = cm.get("params") or {}
    for key in ("working_memory_messages", "max_in_turn_messages", "max_messages"):
        raw = params.get(key)
        if raw is not None:
            try:
                return max(0, int(raw))
            except (TypeError, ValueError):
                break
    return 20


@dataclass
class WorkingMemoryStore:
    messages: list[dict[str, Any]] = field(default_factory=list)
    _open_tool_call_id: str = field(default="", repr=False)

    def clear(self) -> None:
        self.messages.clear()
        self._open_tool_call_id = ""

    def record_assistant_tool_call(
        self,
        *,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        self._open_tool_call_id = call_id
        self.messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(dict(arguments or {})),
                        },
                    }
                ],
            }
        )

    def record_assistant_tool_calls(
        self,
        calls: list[tuple[str, str, dict[str, Any]]],
    ) -> None:
        if not calls:
            return
        self._open_tool_call_id = calls[0][0] if len(calls) == 1 else ""
        self.messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(args),
                        },
                    }
                    for call_id, tool_name, args in calls
                ],
            }
        )

    def record_tool_result(self, *, call_id: str, content: str) -> None:
        resolved = call_id or self._open_tool_call_id
        if not resolved:
            raise ValueError("tool result requires call_id (no matching assistant tool_call)")
        self.messages.append(
            {"role": "tool", "tool_call_id": resolved, "content": content}
        )
        if resolved == self._open_tool_call_id:
            self._open_tool_call_id = ""

    def record_assistant_message(self, content: str) -> None:
        if content.strip():
            self.messages.append({"role": "assistant", "content": content})


@dataclass(frozen=True)
class WorkingMemoryContextSource:
    """Queried by context manager — not generic L2 memory / RAG."""

    store: WorkingMemoryStore
    source_type: str = SOURCE_TYPE
    mechanism: str = "inject"

    def collect_context(self, *, manifest: dict | None = None, **_: Any) -> list[dict[str, Any]]:
        limit = _slice_limit(manifest)
        if limit <= 0 or not self.store.messages:
            return []
        msgs = self.store.messages
        start = max(0, len(msgs) - limit)
        # Don't slice into the middle of a tool-call group: if the first
        # message after slicing is a "tool" response, back up to include
        # the preceding assistant message with tool_calls.
        while start > 0 and msgs[start].get("role") == "tool":
            start -= 1
        return list(msgs[start:])


def working_memory_source(store: WorkingMemoryStore) -> WorkingMemoryContextSource:
    return WorkingMemoryContextSource(store=store)
