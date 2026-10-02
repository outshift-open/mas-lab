#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LLM advertisement over ControlContract. The tool is not the implementation."""

from __future__ import annotations

import json
from typing import Any


class ControlTools:
    """Bounded LLM surface: pause, inspect, list, navigate, cancel — same SessionControl."""

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
            {
                "name": "inspect_session",
                "description": "Inspect live vs debug-cursor snapshot ids for this session.",
                "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
            },
            {
                "name": "navigate_checkpoint",
                "description": "Move the debug cursor. Does not change the live run until promote.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "to": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["to", "reason"],
                },
            },
            {
                "name": "cancel_inflight",
                "description": "Cancel the in-flight LLM call. Tools are not rolled back.",
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
        if tool_name == "inspect_session":
            view = self.control.inspect(self.session_id)
            return json.dumps(
                {
                    "session_id": view.session_id,
                    "status": view.status,
                    "turn": view.turn,
                    "live_snapshot_id": view.live_snapshot_id,
                    "cursor_snapshot_id": view.cursor_snapshot_id,
                    "spec_revision": view.spec_revision,
                }
            )
        if tool_name == "navigate_checkpoint":
            ref = self.control.navigate(
                self.session_id,
                to=str(arguments.get("to") or ""),
                reason=str(arguments.get("reason") or ""),
            )
            return getattr(ref, "snapshot_id", str(ref))
        if tool_name == "cancel_inflight":
            cancelled = self.control.cancel_inflight(self.session_id)
            return "cancelled" if cancelled else "idle"
        return f"[control] unsupported tool {tool_name!r}"
