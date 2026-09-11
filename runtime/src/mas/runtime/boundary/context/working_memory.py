#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Working memory — L1 in-turn trajectory (``source_type=working_memory`` context source).

``WorkingMemoryStore`` holds every assistant/tool message for the current kernel
turn (audit and events). **Assembly** does not send the full list to the LLM:
``assemble_llm_messages`` takes only ``bounded_working_memory_tail`` (count
limit from manifest, default 20) and passes that slice as ``pin_tail`` to token
budget trimming. See :mod:`mas.runtime.boundary.context.assemble` for pinning
vs committed-history trimming.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mas.runtime.boundary.context.trim import context_manager_spec
from mas.runtime.spec.defaults import DEFAULT_WORKING_MEMORY_MESSAGES

SOURCE_TYPE = "working_memory"


def working_memory_slice_limit(manifest: dict | None) -> int:
    """Max in-turn working-memory messages kept for assembly (0 = unbounded).

    Restores the pre-#62/#63 default (20): without *some* count-based cap,
    a stuck ReAct loop (the same tool call failing the same way every retry,
    e.g. issue #65) pins every repeat into the prompt for the rest of the
    turn instead of aging the oldest ones out.
    """
    cm = context_manager_spec(manifest)
    params = cm.get("params") or {}
    for key in ("working_memory_messages", "max_in_turn_messages", "max_messages"):
        raw = params.get(key)
        if raw is not None:
            try:
                return max(0, int(raw))
            except (TypeError, ValueError):
                break
    return DEFAULT_WORKING_MEMORY_MESSAGES


def bounded_working_memory_tail(
    messages: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Keep at most the last *limit* messages, never splitting a tool-call group.

    If slicing would start on a ``tool`` message, back up to include the
    preceding assistant message with the matching ``tool_calls`` — the pair
    must travel together or the provider payload is invalid.
    """
    if limit <= 0 or len(messages) <= limit:
        return list(messages)
    start = max(0, len(messages) - limit)
    while start > 0 and messages[start].get("role") == "tool":
        start -= 1
    return list(messages[start:])


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
