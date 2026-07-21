#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Governance facet: decisions, HITL exchanges, and blocked-action markers.

This is a facet in the same sense as ``annotations.py``'s
``_collect_annotations`` / ``_collect_context_provenance``: a pure function
over the flat ``(events, records)`` pair that returns exactly the shape the
DAG builder needs, with no opinion about where that pair came from.

``events`` here can come from a live ``events.jsonl`` trace via
``records.py::_build_call_records``, or from a ``kg.json`` graph via
``kg_adapter.py``'s ``_synthesize_annotation_events`` (which already
reconstructs any ``CallAnnotation`` node — governance decisions and HITL
exchanges included — back into the same flat, kind-tagged event shape
verbatim). Both call paths converge on ``(records, events)`` before reaching
``dag.py._build_dag``, so a future move to a KG-native query only changes how
that pair is produced upstream; the functions below do not change.
"""

from collections import defaultdict
from typing import Any

from mas.lab.plots.multilevel_trajectory.constants import TYPE_COLOR

# Decisions that pre-empt the call the kernel would otherwise have issued —
# there is no engine_io event, and so no execution record, for these.
_TERMINAL_DECISIONS = frozenset({"BLOCK", "TERMINATE", "SKIP", "BLACKLIST"})

# Severity rank per GovernanceAction — the higher the rank, the more a
# decision changed what would otherwise have happened. Used to pick the
# "worst" (most severe) decision when a call carries more than one (e.g. an
# egress ALLOW and an ingress RETRY on the same call), for badge/lane
# coloring. This is the ONLY place this ranking is defined: the frontend
# (assets/multilevel.html) reads the color this module already computed per
# node (TransNode.governance_color / StateNode.governance_color) rather than
# re-deriving it from a second, independently-maintained JS table — two
# copies of this table previously risked silently diverging (they already
# disagreed on the default rank for an unrecognized decision).
_SEVERITY_RANK: dict[str, int] = {
    "BLOCK": 3, "TERMINATE": 3, "BLACKLIST": 3,
    "HITL": 2, "RETRY": 2, "SKIP": 2, "MODIFY": 2,
    "ALLOW": 0, "LOG": 0,
}
# Rank 1 is deliberately unassigned above and used only as the default for a
# decision value neither this table nor the GovernanceAction enum recognizes
# (e.g. a future addition this module hasn't been updated for yet) — it
# should read as "something governance-related happened, look closer", not
# silently render identically to ALLOW.
_SEVERITY_CALL_TYPE: dict[int, str] = {
    3: "GovernanceBlock", 2: "GovernanceCaution", 1: "GovernanceCaution", 0: "GovernanceAllow",
}


def _governance_severity(gdata: list[dict[str, Any]]) -> tuple[str, str, str]:
    """Return ``(worst_decision, call_type, color)`` for a call's governance list.

    ``call_type`` is one of the synthetic GovernanceBlock/Caution/Allow types
    (used to color a dedicated governance-lane bar); ``color`` is that same
    severity's color directly (used for a badge on a call that ISN'T itself a
    governance-lane bar, e.g. a ToolCall with a governance badge overlay).
    Both come from the same single ranking so they can never disagree.
    """
    worst_rank, worst_decision = -1, "ALLOW"
    for g in gdata:
        rank = _SEVERITY_RANK.get(g.get("decision", ""), 1)
        if rank > worst_rank:
            worst_rank, worst_decision = rank, g.get("decision", "ALLOW")
    call_type = _SEVERITY_CALL_TYPE.get(max(worst_rank, 0), "GovernanceAllow")
    return worst_decision, call_type, TYPE_COLOR.get(call_type, "#64748b")


def governance_color(gdata: list[dict[str, Any]]) -> str:
    """Severity color for the worst decision in ``gdata``, or "" when empty.

    Shared by ``StateNode.governance_color`` / ``TransNode.governance_color``
    so the empty-list guard and severity lookup live in one place.
    """
    return _governance_severity(gdata)[2] if gdata else ""


def notable_governance(gdata: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``gdata`` unchanged if its worst decision is notable, else ``[]``.

    Every governed call carries a decision (egress ALLOW at minimum), so
    attaching ``gdata`` unfiltered would put a governance badge on nearly
    every call in the trace — almost always ALLOW, indistinguishable from
    "nothing happened" and redundant with the call's own hover. Badges are
    only useful when something actually changed the outcome (HITL/RETRY/
    SKIP/MODIFY/BLOCK/...); this gates the *badge overlay* on a regular call
    to that case. The dedicated Governance lane (``_gov_intervals`` below)
    intentionally shows every decision including ALLOW — it is opt-in and
    exists specifically for full audit visibility, so it must not use this.
    """
    if not gdata:
        return []
    _, call_type, _ = _governance_severity(gdata)
    return gdata if call_type != "GovernanceAllow" else []


def _collect_governance_decisions(
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Return ``call_id -> [{hook, checkpoint, decision, reason, policyName}, ...]``.

    A ``governance_decision`` event carries the same ``correlation_id`` as the
    engine call it gates (egress before the call, ingress after it returns),
    so matching by ``(agent_id, correlation_id)`` is exact — no timestamp
    heuristics needed, unlike the annotation matching in ``annotations.py``.
    """
    call_id_by_corr: dict[tuple[str, Any], str] = {}
    for rec in records:
        corr = rec.get("correlation_id")
        if corr is not None:
            call_id_by_corr.setdefault((rec.get("agent_id", ""), corr), rec["call_id"])

    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        if ev.get("kind") != "governance_decision" or not ev.get("decision"):
            continue
        cid = call_id_by_corr.get((ev.get("agent_id", ""), ev.get("correlation_id")))
        if cid is None:
            continue
        out[cid].append({
            "hook":       ev.get("hook", ""),
            "checkpoint": ev.get("checkpoint", ""),
            "decision":   ev.get("decision", ""),
            "reason":     ev.get("reason", ""),
            "policyName": ev.get("policy_name", ""),
        })
    return dict(out)


def _collect_hitl_exchanges(events: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    """Return ``request_id -> {question, offeredActions, resolution, answer}``.

    Pairs each ``hitl_request`` with its ``hitl_resolve`` by the request's own
    id, which the resolve event carries as its ``correlation_id``.
    """
    out: dict[Any, dict[str, Any]] = {}
    for ev in events:
        if ev.get("kind") == "hitl_request":
            rid = ev.get("correlation_id")
            out[rid] = {
                "question":       ev.get("question", ""),
                "offeredActions": ev.get("offered_actions") or [],
                "resolution":     "",
                "answer":         "",
            }
    for ev in events:
        if ev.get("kind") == "hitl_resolve":
            rid = ev.get("correlation_id")
            if rid in out:
                out[rid]["resolution"] = ev.get("resolution", "")
                out[rid]["answer"] = ev.get("answer", "")
    return out


def _collect_blocked_actions(
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return ghost markers for calls governance stopped before they ran.

    A BLOCK/TERMINATE/SKIP/BLACKLIST decision at the egress hook pre-empts
    the engine call the kernel would otherwise have issued, so no execution
    record exists to hang a bar on — without this, the action leaves no
    trace at all in the trajectory. Each entry carries the timestamp and
    agent the block happened at, so the caller can attach it to the nearest
    state boundary instead of a call bar.
    """
    live_corr = {
        (rec.get("agent_id", ""), rec.get("correlation_id"))
        for rec in records
        if rec.get("correlation_id") is not None
    }
    ghosts: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("kind") != "governance_decision":
            continue
        if ev.get("hook") != "egress" or ev.get("checkpoint") != "after":
            continue
        decision = ev.get("decision", "")
        if decision not in _TERMINAL_DECISIONS:
            continue
        key = (ev.get("agent_id", ""), ev.get("correlation_id"))
        if key in live_corr:
            continue
        ghosts.append({
            "agent_id":   ev.get("agent_id", ""),
            "ts":         float(ev.get("timestamp") or 0),
            "decision":   decision,
            "reason":     ev.get("reason", ""),
            "policyName": ev.get("policy_name", ""),
        })
    return ghosts


def _collect_retry_chains(
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return ``call_id -> {groupId, attempt}`` for governance-triggered retries.

    A retry re-issues the same op for the same agent after an ingress RETRY
    decision; the kernel does not reuse the original correlation_id, so
    chains are identified structurally: consecutive same-agent, same-type,
    same-target (tool name or model) records where a RETRY decision's
    timestamp falls in the gap between one attempt's end and the next
    attempt's start.
    """
    retry_ts_by_agent: dict[str, list[float]] = defaultdict(list)
    for ev in events:
        if (
            ev.get("kind") == "governance_decision"
            and ev.get("hook") == "ingress"
            and ev.get("decision") == "RETRY"
        ):
            retry_ts_by_agent[ev.get("agent_id", "")].append(float(ev.get("timestamp") or 0))
    if not retry_ts_by_agent:
        return {}

    _ENGINE_TYPES = {"LLMCall", "ToolCall", "MemoryCall", "RAGQuery"}
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        if rec.get("call_type") in _ENGINE_TYPES:
            by_agent[rec.get("agent_id", "")].append(rec)

    out: dict[str, dict[str, Any]] = {}
    for agent_id, recs in by_agent.items():
        retry_ts = sorted(retry_ts_by_agent.get(agent_id, []))
        if not retry_ts:
            continue
        recs_sorted = sorted(recs, key=lambda r: r["start_ts"])
        chain: list[dict[str, Any]] = [recs_sorted[0]]
        group_id = ""
        for rec in recs_sorted[1:]:
            prev = chain[-1]
            same_op = (
                prev.get("call_type") == rec.get("call_type")
                and prev.get("tool_name") == rec.get("tool_name")
                and prev.get("model") == rec.get("model")
            )
            retried = same_op and any(
                prev["end_ts"] - 1e-6 <= t <= rec["start_ts"] + 1e-6 for t in retry_ts
            )
            if retried:
                chain.append(rec)
                if len(chain) == 2:
                    # First confirmed link in this chain — group_id is fixed
                    # for the chain's lifetime, and the first attempt is only
                    # written once, here (every later attempt writes just
                    # itself, not the whole chain again).
                    group_id = chain[0]["call_id"]
                    out[group_id] = {"groupId": group_id, "attempt": 1}
                out[rec["call_id"]] = {"groupId": group_id, "attempt": len(chain)}
            else:
                chain = [rec]
                group_id = ""
    return out
