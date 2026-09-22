#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stub telemetry tools for the undeclared-tool example agent.

These return canned payloads. They exist so ``mas-ctl chat`` can offer
``get_metrics`` / ``get_logs`` / ``get_service_health``. ``get_deployments``
is intentionally not a tool on this agent.
"""

from __future__ import annotations

from typing import Any

from mas.runtime.contracts import ToolContract


class TelemetryStub(ToolContract):
    """One listed telemetry name. Constructor ``name`` comes from the Tool manifest."""

    def __init__(self, name: str, description: str = "", **_: Any) -> None:
        self._name = name
        self._description = description or f"Stub {name}."

    def on_collect_tools(self, **_: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Canonical service name.",
                        }
                    },
                    "required": ["service"],
                },
            }
        ]

    def on_execute_tool(self, tool_name: str, arguments: dict[str, Any], **_: Any) -> Any:
        if tool_name != self._name:
            return None
        service = str(arguments.get("service") or "")
        return {"service": service, "tool": tool_name, "status": "ok"}
