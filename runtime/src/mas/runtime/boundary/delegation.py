#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation tools — agent-as-tool from workflow / collaboration spec."""

from __future__ import annotations

from typing import Any


def delegation_targets(manifest: dict | None) -> list[str]:
    if not manifest:
        return []
    spec = manifest.get("spec") or {}
    collab = spec.get("collaboration") or {}
    if str(collab.get("mode", "")).lower() in ("none", ""):
        return []
    workflow = spec.get("workflow") or {}
    nodes = workflow.get("nodes") or []
    targets: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for target in node.get("delegates_to") or []:
            if target and target not in targets:
                targets.append(str(target))
    return targets


def openai_delegation_tools(manifest: dict | None) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for agent_id in delegation_targets(manifest):
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"delegate_to_{agent_id}",
                    "description": f"Delegate a sub-task to agent {agent_id}.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": "Task for the delegate agent."},
                        },
                        "required": ["task"],
                    },
                },
            }
        )
    return tools
