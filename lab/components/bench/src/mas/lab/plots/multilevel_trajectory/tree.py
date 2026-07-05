#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Call tree construction and lane sequence derivation."""

from collections import defaultdict
from typing import Optional

from mas.lab.plots.multilevel_trajectory.constants import _TS_TOL

def _build_call_tree(
    records: list[dict],
) -> tuple[dict[str, list[dict]], dict[str, Optional[str]]]:
    """Compute parent–child relationships between execution records.

    Uses ``parent_call_id`` exclusively for all record types — O(n), exact.
    This is possible because the runtime now propagates ``parent_exec_call_id``
    through the task payload for every delegation (Local, agent-remote, gRPC…), so
    ``execution_start`` events for sub-agents carry the correct parent link
    without any temporal containment heuristic.

    Returns
    -------
    children_of : {call_id: [child_record, …]} sorted by ``start_ts``
    parent_of   : {call_id: parent_call_id or None}
    """
    children_of: dict[str, list[dict]] = defaultdict(list)
    parent_of:   dict[str, Optional[str]] = {}

    for rec in records:
        pid = rec.get("parent_call_id")
        parent_of[rec["call_id"]] = pid
        if pid is not None:
            children_of[pid].append(rec)

    for cid in children_of:
        children_of[cid].sort(key=lambda r: r["start_ts"])

    return dict(children_of), parent_of


# ---------------------------------------------------------------------------
# Stage 2b — Structural boundary alignment
# ---------------------------------------------------------------------------

def _align_record_boundaries(
    records: list[dict],
    children_of: dict[str, list[dict]],
) -> None:
    """Align start/end timestamps between parents and children using the call
    tree topology.  No timestamp thresholds — purely structural.

    Rules applied for each parent's sorted children list:

    1. **First child** → ``child.start_ts = parent.start_ts``
       The first work item begins the instant the parent begins; the delta
       between ``execution_start`` and ``llm_call_start`` is Python overhead.

    2. **Consecutive siblings** → ``child_i.end_ts = child_{i+1}.start_ts``
       Adjacent work items share exactly one boundary state; no gap or overlap.

    3. **Last child** → ``child.end_ts = parent.end_ts``
       The last work item finishes when the parent finishes.

    Modifies records in-place through the shared dicts in ``children_of``.

    Note on processing gaps: when ``ProcessingCall`` records exist in the
    call tree (e.g. per-actor context injection spans), they participate in
    Rules 1–3 and naturally occupy the gap between the agent boundary and the first
    substantive call.  When no such record exists the gap is simply absorbed
    by Rule 1/3 — the absence is detectable by the caller via
    ``_make_call_sequence`` returning no ProcessingCall at fragment edges.
    """
    rec_by_id = {r["call_id"]: r for r in records}
    for pid, kids in children_of.items():
        parent = rec_by_id.get(pid)
        if parent is None or not kids:
            continue
        sk = sorted(kids, key=lambda r: r["start_ts"])
        # Governance-orphaned LLM calls (no llm_call_end) have synthetic
        # boundaries; applying Rules 1 & 3 to their children (e.g. ToolCalls
        # for memory_search) would corrupt the children's real event
        # timestamps.  Skip both rules in that case so children keep their
        # accurate start/end from the emitted events.
        _orphan_llm_parent = (
            parent.get("_end_missing") and parent.get("call_type") == "LLMCall"
        )
        # Any parent whose end_ts is synthetic (no *_end event was emitted,
        # so it was set to start + 1.0 s or t_final as a structural fallback)
        # must not have Rule 3 applied: snapping the last child to an inflated
        # synthetic boundary corrupts the child's real event timestamp.
        # Classic case: the entry-agent AgentCall (e.g. "sre") never receives
        # an execution_end in multi-agent delegation traces; its end_ts is
        # extended to t_final, and without this guard the last ToolCall
        # (the delegation tool) would be stretched across the entire trace.
        _orphan_parent = parent.get("_end_missing", False)
        # Rule 1 — snap the first work item (including ProcessingCall) to the
        # parent boundary.  The delta between execution_start and the first
        # child is pure Python/instrumentation overhead and must not appear
        # as a visible gap column.
        if not _orphan_llm_parent:
            sk[0]["start_ts"] = parent["start_ts"]
        # Rule 3 — last child shares the parent's end boundary.
        # Skip for any parent with a synthetic end_ts (_end_missing).
        if not _orphan_parent:
            sk[-1]["end_ts"] = parent["end_ts"]
        # Rule 2 (consecutive siblings share boundaries — sequential only).
        # Skip when two children start at the same timestamp (parallel
        # execution, e.g. a moderator dispatching 3 agents concurrently):
        # naive closure would shrink the earlier record to zero-duration,
        # hiding its call-lane children entirely.
        for i in range(len(sk) - 1):
            if sk[i + 1]["start_ts"] > sk[i]["start_ts"] + _TS_TOL:
                sk[i]["end_ts"] = sk[i + 1]["start_ts"]


# ---------------------------------------------------------------------------
# Stage 3a — Agent lane sequence: DFS on agent subtree
# ---------------------------------------------------------------------------

def _make_agent_sequence(
    records:     list[dict],
    children_of: dict[str, list[dict]],
    parent_of:   dict[str, Optional[str]],
) -> list[dict]:
    """Return the ordered list of agent-level records for the Agent lane.

    Delegation (``moderator`` spawning ``scheduler``) is resolved by DFS:
    the parent record is split into *pre-child* fragments (output cleared,
    parent still running) and a *tail* fragment (parent has finished,
    output is known).  The children are interleaved between the fragments.

    Example::

        moderator(0→10) delegates scheduler(4→8) →

        moderator_pre (0→4, output="")   ← parent running, no output yet
        scheduler     (4→8)
        moderator_tail(8→10)             ← parent done, output available

    No heuristics — boundaries come exclusively from the call tree.
    """
    rec_by_id = {r["call_id"]: r for r in records}

    def _has_agent_ancestor(rec: dict) -> bool:
        pid = parent_of.get(rec["call_id"])
        while pid is not None:
            if rec_by_id.get(pid, {}).get("level") == "agent":
                return True
            pid = parent_of.get(pid)
        return False

    agent_roots = sorted(
        [r for r in records if r["level"] == "agent" and not _has_agent_ancestor(r)],
        key=lambda r: r["start_ts"],
    )

    result: list[dict] = []

    def dfs(rec: dict) -> None:
        agent_children = sorted(
            [c for c in children_of.get(rec["call_id"], []) if c["level"] == "agent"],
            key=lambda c: c["start_ts"],
        )
        if not agent_children:
            result.append(rec)
            return

        # Merge overlapping ranges of child agents.
        merged: list[tuple[float, float]] = []
        for ac in agent_children:
            if merged and ac["start_ts"] <= merged[-1][1] + _TS_TOL:
                merged[-1] = (merged[-1][0], max(merged[-1][1], ac["end_ts"]))
            else:
                merged.append((ac["start_ts"], ac["end_ts"]))

        pos = rec["start_ts"]
        for (cs, ce) in merged:
            if cs - pos > _TS_TOL:
                result.append({**rec, "start_ts": pos, "end_ts": cs,
                                "output": "", "_fragment": True})
            for ac in agent_children:
                if ac["start_ts"] >= cs - _TS_TOL and ac["end_ts"] <= ce + _TS_TOL:
                    dfs(ac)
            pos = ce

        if rec["end_ts"] - pos > _TS_TOL:
            result.append({**rec, "start_ts": pos, "end_ts": rec["end_ts"]})

    for root in agent_roots:
        dfs(root)

    result.sort(key=lambda r: r["start_ts"])
    return result


# ---------------------------------------------------------------------------
# Stage 3b — Call lane: direct call children of each agent fragment
# ---------------------------------------------------------------------------

def _make_call_sequence(
    agent_sequence: list[dict],
    children_of:    dict[str, list[dict]],
) -> list[dict]:
    """Return the ordered list of call-level records for the Call lane.

    For each agent record fragment we collect the *direct* call-level children
    (LLMCall, ToolCall, MemoryCall, RAGQuery, ProcessingCall) via the
    ``parent_call_id``-based call tree.

    **Delegation tool filtering** (structural, zero name heuristics):

    A ToolCall is a *delegation tool* when its children in the call tree
    include at least one AgentCall record (``children_of[tool_id]`` contains
    a record with ``level == "agent"``).  Such tools are skipped because the
    agent lane already represents the delegated execution.
    """
    def _is_delegation_tool(rec: dict) -> bool:
        if rec["call_type"] != "ToolCall":
            return False
        # A delegation tool wraps a sub-agent execution: its children in the
        # call tree include at least one AgentCall record.
        return any(c["level"] == "agent" for c in children_of.get(rec["call_id"], []))

    result:   list[dict] = []
    seen_ids: set[str]   = set()

    def _collect(
        call_id: str,
        ts_start: float,
        ts_end: float,
        *,
        _ancestors: frozenset[str] = frozenset(),
    ) -> None:
        """Collect direct call-level children of ``call_id`` that fall within
        the fragment window ``[ts_start, ts_end]``.

        The window filter is needed when the same agent execution is split into
        multiple fragments by ``_make_agent_sequence`` (DFS interleaving):
        all fragments share the same ``call_id``, but each fragment must only
        claim calls that start within its time slice.
        """
        if call_id in _ancestors:
            return
        next_ancestors = _ancestors | {call_id}
        for child in children_of.get(call_id, []):
            if child["level"] != "call":
                continue
            if child["start_ts"] < ts_start - _TS_TOL:
                continue
            if child["start_ts"] > ts_end + _TS_TOL:
                continue
            if child["call_id"] in seen_ids:
                continue
            # Delegation tools are covered by the agent lane — skip them.
            if _is_delegation_tool(child):
                continue
            # Governance-orphaned LLM calls are implementation artifacts:
            # governance intercepted the call before it completed and no
            # llm_call_end was emitted.  Showing them would produce two
            # consecutive LLM-call bars with no state node between them,
            # which is semantically invalid.  We still recurse so that any
            # ToolCall / non-LLM descendants (e.g. memory_search whose
            # parent_call_id points to the orphaned call) are promoted to
            # the call lane.
            is_orphan_llm = (
                child.get("_end_missing") and child["call_type"] == "LLMCall"
            )
            if not is_orphan_llm:
                result.append(child)
                seen_ids.add(child["call_id"])
            # Recurse for calls nested under non-LLM parents (e.g. ToolCall
            # wrapping sub-calls).  LLMCalls are leaves in new traces; but in
            # older traces a governance short-circuit leaves a stale LLM
            # call_id on the stack causing the next step's calls to be parented
            # under it — recurse in that case too so those calls are visible.
            if child["call_type"] != "LLMCall" or children_of.get(child["call_id"]):
                _collect(
                    child["call_id"],
                    child["start_ts"],
                    child["end_ts"],
                    _ancestors=next_ancestors,
                )

    for arec in agent_sequence:
        _collect(arec["call_id"], arec["start_ts"], arec["end_ts"])

    # Sort chronologically.  The tree-recursion order can put a child (e.g.
    # a ToolCall nested under a governance-orphaned LLMCall) before its
    # sibling that starts earlier in wall-clock time, causing xr_nat < xl
    # in the JS renderer and making calls invisible.  Sorting by start_ts
    # restores the natural time ordering; LLM calls always precede their
    # own ToolCall children so parent-before-child order is preserved.
    result.sort(key=lambda r: r["start_ts"])
    return result
