#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""System tool advertisement for bounded, pre-authored subagent templates."""

from __future__ import annotations

from typing import Any

from mas.runtime.engine.tools import SPAWN_SUBAGENT_TOOL


class SpawnSubagentTool:
    """Advertise spawn_subagent only when the manifest grants the capability."""

    def on_collect_tools(self, *, ctx: Any = None) -> list[dict[str, Any]]:
        if not getattr(ctx, "allow_subagent_spawning", False):
            return []
        templates = list(getattr(ctx, "subagent_templates", []) or [])
        if not templates:
            return []
        template_ids = [str(template["id"]) for template in templates]
        descriptions = [
            f"{template['id']}: {template.get('description', '')}".rstrip(": ")
            for template in templates
        ]
        return [
            {
                "name": SPAWN_SUBAGENT_TOOL,
                "description": "Run one bounded subagent template: " + "; ".join(descriptions),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "template": {
                            "type": "string",
                            "enum": template_ids,
                            "description": "Declared subagent template to run.",
                        },
                        "task": {"type": "string", "minLength": 1},
                    },
                    "required": ["template", "task"],
                },
            }
        ]

    def on_execute_tool(self, tool_name: str, arguments: dict[str, Any], **_: Any) -> str:
        """Fail closed if engine-tool dispatch did not claim the call."""
        return "[spawn_subagent] unavailable: orchestration contract is not wired"