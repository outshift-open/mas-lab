#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LLM advertisement over ControlContract. The tool is not the implementation."""

from __future__ import annotations

from typing import Any


class ControlTools:
    """Bounded LLM surface: pause, inspect, list, navigate — same SessionControl."""

    def __init__(self, control: Any, session_id: str) -> None:
        self.control = control
        self.session_id = session_id

    def on_collect_tools(self, *, ctx: Any = None) -> list[dict[str, Any]]:
        if not getattr(ctx, "allow_control_tools", False):
            return []
        return [
            {
                "name": "pause_session",
                "description": "Pause this session at the next turn boundary.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"reason": {"type": "string"}},
                    "required": ["reason"],
                },
            },
            {
                "name": "list_checkpoints",
                "description": "List snapshot-tree nodes for this session.",
                "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
            },
        ]

    def on_execute_tool(self, tool_name: str, arguments: dict[str, Any], **_: Any) -> str:
        if tool_name == "pause_session":
            self.control.pause(self.session_id, reason=str(arguments.get("reason") or ""))
            return "paused"
        if tool_name == "list_checkpoints":
            nodes = self.control.list_checkpoints(self.session_id)
            return ",".join(n.snapshot_id for n in nodes)
        return f"[control] unsupported tool {tool_name!r}"
