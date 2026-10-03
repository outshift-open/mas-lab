#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""System tool advertisement for bounded, pre-authored subagent templates."""

from __future__ import annotations

from typing import Any

from mas.runtime.engine.tools import (
    CREATE_SUBAGENT_TOOL,
    SPAWN_SUBAGENT_NAMES,
    SPAWN_SUBAGENT_TOOL,
)


class SpawnSubagentTool:
    """Advertise create/spawn_subagent when the manifest grants the capability."""

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
        parameters = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "template": {
                    "type": "string",
                    "enum": template_ids,
                    "description": "Declared subagent template to create and run.",
                },
                "task": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Task for the child. The child cannot invent tools or templates.",
                },
            },
            "required": ["template", "task"],
        }
        catalog = "; ".join(descriptions)
        return [
            {
                "name": CREATE_SUBAGENT_TOOL,
                "description": (
                    "Create a bounded subagent from a declared template and run it "
                    "for one turn. Templates: " + catalog
                ),
                "parameters": parameters,
            },
            {
                "name": SPAWN_SUBAGENT_TOOL,
                "description": "Same as create_subagent. Templates: " + catalog,
                "parameters": parameters,
            },
        ]

    def on_execute_tool(self, tool_name: str, arguments: dict[str, Any], **_: Any) -> str:
        """Fail closed if engine-tool dispatch did not claim the call."""
        if tool_name not in SPAWN_SUBAGENT_NAMES:
            return f"[spawn_subagent] unsupported tool {tool_name!r}"
        return "[spawn_subagent] unavailable: orchestration contract is not wired"
