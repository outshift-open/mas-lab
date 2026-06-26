#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""KG data extraction for message graphs."""

import bisect

from mas.lab.plots.kg_adapter import KGView

# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

def _extract(view: KGView) -> tuple[list[dict], dict[str, list[dict]]]:
    """Return (llm_calls sorted by start_ts, tool_calls keyed by associated LLM call_id).

    Uses :class:`~mas.lab.plots.kg_adapter.KGView` for normalized field access.
    ToolCalls have ``parent_call_id`` pointing to AgentCalls (not LLMCalls);
    each top-level ToolCall is associated with the most recent LLM call from
    the **same agent** whose ``start_ts`` is ≤ the tool call's ``start_ts``.
    """
    llm_calls: list[dict] = view.query("LLMCall")  # already sorted by start_ts

    # Build per-agent sorted list of (start_ts, call_id) for binary search
    llm_times_by_agent: dict[str, list[tuple[float, str]]] = {}
    for c in llm_calls:
        agent = c["agent_id"]
        llm_times_by_agent.setdefault(agent, []).append((c["start_ts"], c["call_id"]))
    # Lists already in order (records sorted by start_ts), but sort to be safe
    for lst in llm_times_by_agent.values():
        lst.sort()

    tool_by_llm: dict[str, list[dict]] = {}
    for n in view.query("ToolCall"):
        # Only top-level tool calls: parent is an AgentCall, not a ToolCall
        parent = view.get(n["parent_call_id"])
        if parent and parent["call_type"] == "ToolCall":
            continue  # skip nested / chained tool calls

        agent = n["agent_id"]
        t_tool = n["start_ts"]
        times = llm_times_by_agent.get(agent, [])
        if not times:
            continue

        # Find the most recent LLM call with start_ts <= t_tool
        idx = bisect.bisect_right(times, (t_tool, "\uffff")) - 1
        if idx >= 0:
            tool_by_llm.setdefault(times[idx][1], []).append(n)

    return llm_calls, tool_by_llm


def _find_root_agent_id(view: KGView) -> str | None:
    """Return the agent_id of the root AgentCall (the one with no parent_call_id)."""
    for ac in view.query("AgentCall", parent_call_id=None):
        return ac["agent_id"]
    return None


def _assign_iterations(
    llm_calls: list[dict],
    root_agent_id: str | None,
) -> list[int]:
    """Assign an iteration index to each LLM call.

    Each LLM call made by the root agent starts a new iteration.
    All other LLM calls inherit the iteration of the most recent root LLM call
    that began at or before their own ``startTime``.

    For SRE triage (root = sre, 8 sre calls):
    - Iter 0: sre#1 + telemetry#1-4
    - Iter 1: sre#2 + backend#1-4
    - Iter 2: sre#3 + db#1-2
    - etc.
    """
    if not root_agent_id or not llm_calls:
        return [0] * len(llm_calls)

    root_start_times: list[float] = sorted(
        c["start_ts"]
        for c in llm_calls
        if c["agent_id"] == root_agent_id
    )
    if not root_start_times:
        return [0] * len(llm_calls)

    result: list[int] = []
    for c in llm_calls:
        idx = bisect.bisect_right(root_start_times, c["start_ts"]) - 1
        result.append(max(0, idx))
    return result
