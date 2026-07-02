#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation policy — MAS workflow topology → ``delegate_to_*`` tool surface.

Peer tools are exposed when ``workflow.type`` is dynamic (default).
``spec.collaboration`` is validated at ctl compose time (omit or ``type: none``).
"""

from __future__ import annotations

from typing import Any

DELEGATE_TOOL_PREFIX = "delegate_to_"
_NO_PEER_DELEGATION = frozenset({"sequential", "linear", "pipeline", "single"})
_DELEGATE_PARAMS = {
    "type": "object",
    "properties": {"task": {"type": "string", "description": "Task for the delegate agent."}},
    "required": ["task"],
}


def _spec(manifest: dict | None) -> dict[str, Any]:
    return (manifest or {}).get("spec") or {}


def _workflow(manifest: dict | None) -> dict[str, Any]:
    wf = _spec(manifest).get("workflow")
    return wf if isinstance(wf, dict) else {}


def workflow_type(manifest: dict | None) -> str:
    return str(_workflow(manifest).get("type") or "dynamic").strip().lower()


def uses_llm_peer_delegation(manifest: dict | None) -> bool:
    return workflow_type(manifest) not in _NO_PEER_DELEGATION


def entry_agent_id(manifest: dict | None) -> str | None:
    wf = _workflow(manifest)
    if entry := wf.get("entry"):
        return str(entry)
    name = ((manifest or {}).get("metadata") or {}).get("name")
    return str(name) if name else None


def delegation_targets(manifest: dict | None, *, agent_id: str | None = None) -> list[str]:
    if not manifest or not uses_llm_peer_delegation(manifest):
        return []
    nodes = [n for n in (_workflow(manifest).get("nodes") or []) if isinstance(n, dict)]
    if not nodes:
        return []
    aid = agent_id or entry_agent_id(manifest)
    if aid:
        for node in nodes:
            if str(node.get("id") or "") == aid:
                return [str(t) for t in (node.get("delegates_to") or []) if t]
        return []
    seen: list[str] = []
    for node in nodes:
        for target in node.get("delegates_to") or []:
            s = str(target)
            if s and s not in seen:
                seen.append(s)
    return seen


def delegate_tool_name(agent_id: str) -> str:
    return f"{DELEGATE_TOOL_PREFIX}{agent_id}"


def parse_delegate_tool_name(tool_name: str) -> str | None:
    if not tool_name.startswith(DELEGATE_TOOL_PREFIX):
        return None
    target = tool_name[len(DELEGATE_TOOL_PREFIX) :].strip()
    return target or None


def openai_delegation_tools(manifest: dict | None, *, agent_id: str | None = None) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": delegate_tool_name(peer),
                "description": f"Delegate a sub-task to agent {peer}.",
                "parameters": _DELEGATE_PARAMS,
            },
        }
        for peer in delegation_targets(manifest, agent_id=agent_id)
    ]
