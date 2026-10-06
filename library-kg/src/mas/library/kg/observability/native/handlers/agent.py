#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the ``execution_start`` / ``execution_end`` event kinds.

Produces an AgentCall or TaskCall node (``_class_for_event`` already refined
AgentCall -> TaskCall by the event's ``boundary``/``agent_id`` fields during
classification). Also carries the routing-derived ``parent_call_id``
inference: since ``execution_start``/``execution_end`` and ``routing``
events arrive in a single arrival-ordered stream, the builder's
``_active_exec`` / ``_pending_parent`` dicts (populated here and in
``handlers/annotation.py``'s routing handling) can infer a sub-agent's
delegation parent from the most recent ``routing`` event addressed to it,
when the runtime itself didn't set ``parent_call_id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from mas.library.kg.core.native_graph_builder import NativeGraphBuilder


def handle_agent_call(event: Dict[str, Any], builder: "NativeGraphBuilder") -> List[Dict[str, Any]]:
    kind = event.get("kind", "")
    agent_id = event.get("agent_id", "")
    local_name = event.get("mas_class", "AgentCall")

    if kind == "execution_start":
        # Real explicit parent_call_id (set by the runtime) always wins;
        # only fill the gap with the routing-derived guess when the runtime
        # left it empty. A third, timestamp-containment-derived fallback
        # (core.graph_builder._backfill_missing_parent_call_ids) runs later,
        # in finalize(), for whatever both of these still leave unset.
        if not event.get("parent_call_id"):
            inferred = builder._pending_parent.pop(agent_id, None)
            if inferred:
                event["parent_call_id"] = inferred
        # rewrite_tool_delegation: LangGraph / norm treat delegated
        # AgentCalls as siblings (ioa_observe.agent.previous), not as
        # children of the caller or of the intercepted delegate_to_* tool.
        if getattr(builder, "rewrite_tool_delegation", True):
            parent = str(event.get("parent_call_id") or "")
            rewritten = getattr(builder, "_rewritten_delegate_ids", set())
            if parent and parent in rewritten:
                event["parent_call_id"] = None

    if kind == "execution_end":
        active = builder._active_exec.get(agent_id)
        if active and active != event.get("call_id"):
            event = dict(event)
            event["call_id"] = active
    node = builder.upsert_call(event, local_name)

    if kind == "execution_start":
        if node is not None:
            builder._active_exec[agent_id] = node["callId"]
        if local_name == "TaskCall":
            if node is not None:
                node.setdefault("taskName", event.get("task_name") or node.get("kindBase", ""))
                node.setdefault("taskType", event.get("task_type", ""))
        else:
            if node is not None:
                node.setdefault("agentName", event.get("agent_id", node.get("agentId", "")))
                node.setdefault("agentType", event.get("agent_type", ""))
                node.setdefault("inputContent", event.get("input") or event.get("payload") or "")
                if event.get("agent_sequence"):
                    node.setdefault("agentSequence", int(event["agent_sequence"]))
    elif kind == "execution_end":
        builder._active_exec.pop(agent_id, None)
        if node is not None and local_name != "TaskCall":
            node["outputRaw"] = event.get("output") or event.get("payload") or ""

    return [node] if node is not None else []
