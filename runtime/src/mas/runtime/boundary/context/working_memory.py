#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Working memory — L1 in-turn trajectory (``source_type=working_memory`` context source)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

SOURCE_TYPE = "working_memory"


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
