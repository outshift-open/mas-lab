#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Annotation and context-provenance hover enrichment."""

from collections import defaultdict
from typing import Optional

from mas.lab.plots.multilevel_trajectory.constants import _TS_TOL

# State hover priority: the most specific (deepest) level's output wins when
# multiple transitions end at the same timestamp.
# ``agent_end`` (=4) is used at agent-result boundaries so the agent's
# authoritative output takes precedence over call-layer bookkeeping values
# (e.g. ``next_inp`` of the next call that happens to share the same ts).
_HOVER_PRIORITY: dict[str, int] = {
    "session":   0,
    "mas":       1,
    "agent":     2,
    "call":      3,
    "agent_end": 4,
}


# ---------------------------------------------------------------------------
# Annotation collection — L2/L3 XAI context attached to hover text
# ---------------------------------------------------------------------------

_ANNOTATION_KINDS: frozenset[str] = frozenset({
    "routing",
    "routing_result",
    "context_assembled",
    "governance_authorize_start",
    "governance_authorize_end",
    "governance_validate_start",
    "governance_validate_end",
    "obs_wrap_gov_authorize_start",
    "obs_wrap_gov_authorize_end",
    "obs_wrap_gov_validate_start",
    "obs_wrap_gov_validate_end",
    "observability_pre_execute_start",
    "observability_post_execute_end",
    "state_update_start",
    "state_update_end",
    "agent_communication_start",
    "agent_communication_end",
})

_ANNOTATION_LABEL: dict[str, str] = {
    "routing":                   "→ routing",
    "routing_result":            "→ routed",
    "context_assembled":         "ctx",
    "state_update_start":        "state↑",
    "state_update_end":          "state↓",
    "agent_communication_start": "agent-remote↑",
    "agent_communication_end":   "agent-remote↓",
}


def _collect_annotations(
    events:  list[dict],
    records: list[dict],
) -> dict[str, list[str]]:
    """Return ``call_id \u2192 [annotation_summary_line, ...]`` for L2/L3 XAI hover enrichment.

    Annotation events (routing, context_assembled, …) are matched to the
    *narrowest* enclosing call record by ``agent_id`` + timestamp containment.
    Events without a matching record are silently skipped.
    """
    ann_events = [e for e in events if e.get("kind") in _ANNOTATION_KINDS]
    if not ann_events:
        return {}

    result: dict[str, list[str]] = defaultdict(list)

    for ann in ann_events:
        ann_ts    = float(ann.get("timestamp") or 0)
        ann_agent = ann.get("agent_id", "")
        kind      = ann.get("kind", "")

        best_rec: Optional[dict] = None
        best_dur  = float("inf")
        for rec in records:
            if rec.get("agent_id") != ann_agent:
                continue
            s = float(rec.get("start_ts") or 0)
            e = float(rec.get("end_ts")   or 0)
            if s <= ann_ts <= e and (e - s) < best_dur:
                best_dur = e - s
                best_rec = rec

        if best_rec is None:
            continue

        label = _ANNOTATION_LABEL.get(kind, kind)
        parts = [label]
        # Extract the most meaningful payload field for the short summary
        for _f in ("target_agent_id", "target", "to", "task"):
            val = ann.get(_f)
            if val:
                parts.append(str(val))
                break
        if kind == "context_assembled":
            segs   = ann.get("segments")
            tokens = ann.get("total_tokens")
            if segs   is not None:
                parts.append(f"{segs} seg")
            if tokens is not None:
                parts.append(f"{tokens} tok")
        if kind in ("state_update_start", "state_update_end"):
            action = ann.get("update_type")
            if action:
                parts.append(str(action))
            preview = ann.get("content_preview")
            if preview:
                parts.append(str(preview)[:40])
        result[best_rec["call_id"]].append(" ".join(parts))

    return dict(result)


# ── Mechanism colour badges ──────────────────────────────────────────────

_MECH_BADGE: dict[str, str] = {
    "inject":    "🔵",
    "rag":       "🟣",
    "tool_call": "🟠",
}

_CAUSE_BADGE_MAP: dict[str, str] = {
    "deterministic": "⚙",
    "stochastic":    "🎲",
    "explicit":      "👤",
}


def _source_category(source: str, mechanism: str = "inject") -> str:
    """Derive a human-readable category from a CPR source name.

    Category is determined by the **source** (where the data comes from),
    not the mechanism (how it was retrieved).  RAG is a mechanism, not a source.
    """
    sl = source.lower()
    if sl.startswith("memory:") or sl.startswith("mem:"):
        return "MEMORY"
    if "skill" in sl or sl.startswith("facet:skill"):
        return "SKILL"
    if sl.startswith("context/role"):
        return "SYSTEM"
    if sl.startswith("context/intent"):
        return "SYSTEM"
    if sl.startswith("context/"):
        return "SYSTEM"
    if sl.startswith("tool:") or sl.startswith("tool_result"):
        return "TOOL"
    if mechanism == "tool_call":
        return "TOOL"
    return "CONTEXT"


def _collect_context_provenance(
    events:  list[dict],
    records: list[dict],
) -> dict[str, list[dict]]:
    """Return ``call_id → [cpr_event, …]`` for L4 context provenance hover enrichment.

    ``context_part_contributed`` events are matched to LLM call records using
    three strategies in priority order:

    1. **Explicit UUID match**: ``ev.llm_call_id`` directly equals a record's
       ``call_id`` (best case — runtime emits the UUID).

    2. **Synthetic-ID mapping**: The runtime's inner layer emits
       ``context_assembled`` events with a synthetic ``call_id`` like "llm-1"
       at the same timestamp as the outer ``llm_call_start``.  We build a
       ``synthetic_id → real_uuid`` map from these events so that CPR events
       with ``llm_call_id="llm-1"`` are redirected to the correct record.

    3. **"Next LLM call" containment**: CPR events fire *during context
       assembly*, which happens just before the LLM call starts — so their
       timestamp is slightly earlier than the LLM call's ``start_ts``.
       We find the nearest LLM record that starts within a short window after
       the CPR event.  The agent_id filter is relaxed for generic ``"agent"``
       values (the runtime emits a placeholder when the per-turn agent id is
       not yet known at context-assembly time).
    """
    cpr_events = [e for e in events if e.get("kind") == "context_part_contributed"]
    if not cpr_events:
        return {}

    llm_records = [r for r in records if r.get("call_type") == "LLMCall"]

    # --- Strategy 2: build synthetic→real mapping from context_assembled ----
    # context_assembled inner events carry call_id="llm-N" (synthetic) at
    # roughly the same timestamp as the matching outer llm_call_start (UUID).
    synth_to_real: dict[str, str] = {}
    ca_events = [e for e in events if e.get("kind") == "context_assembled" and e.get("llm_call_id")]
    for ca in ca_events:
        synth_id = str(ca["llm_call_id"])
        if not synth_id:
            continue
        ca_ts = float(ca.get("timestamp") or 0)
        # Find the closest LLM record by start timestamp (50 ms tolerance).
        best = min(
            llm_records,
            key=lambda r: abs(r["start_ts"] - ca_ts),
            default=None,
        )
        if best is not None and abs(best["start_ts"] - ca_ts) <= 0.05:
            synth_to_real[synth_id] = best["call_id"]

    result: dict[str, list[dict]] = defaultdict(list)

    for ev in cpr_events:
        raw_cid = ev.get("llm_call_id") or ""

        # Strategy 1: direct UUID match
        if raw_cid:
            matched = next((r for r in llm_records if r["call_id"] == raw_cid), None)
            if matched:
                result[matched["call_id"]].append(ev)
                continue

        # Strategy 2: synthetic-ID → real UUID
        if raw_cid and raw_cid in synth_to_real:
            result[synth_to_real[raw_cid]].append(ev)
            continue

        # Strategy 3: nearest LLM call that starts *after* this CPR event.
        # Context assembly fires just before the LLM call that will consume it.
        # Use a generous look-ahead window (500 ms) and relax the agent_id
        # filter when agent_id is the generic placeholder "agent".
        ev_ts    = float(ev.get("timestamp") or 0)
        ev_agent = ev.get("agent_id", "")
        _generic_agent = ev_agent in ("", "agent")

        best_rec: Optional[dict] = None
        best_gap  = float("inf")
        for rec in llm_records:
            if not _generic_agent and rec.get("agent_id") != ev_agent:
                continue
            gap = rec["start_ts"] - ev_ts
            # Accept records whose start is within [−_TS_TOL, +0.5s] of the
            # CPR event: negative gap (CPR fires slightly after start) is
            # possible when the runtime emits context_part_contributed events
            # during the first few ms of the LLM call window.
            if -_TS_TOL <= gap <= 0.5 and gap < best_gap:
                best_gap = gap
                best_rec = rec

        if best_rec:
            result[best_rec["call_id"]].append(ev)

    return dict(result)


def _format_cpr_hover(cpr_parts: list[dict]) -> str:
    """Format context provenance parts into a readable hover-text block.

    Shows each context part with its source, mechanism badge, and the actual
    content text (up to 300 chars per part).
    """
    if not cpr_parts:
        return ""

    lines: list[str] = ["\n\n📦 Context Assembly:"]
    total_tokens = 0
    for part in cpr_parts:
        source = part.get("source", "?")
        mechanism = part.get("access_mechanism", "inject")
        cause_type = part.get("cause_type", "deterministic")
        tokens = part.get("token_estimate", 0)
        retained = part.get("retained", True)
        content = part.get("content") or part.get("content_preview") or ""
        placement = part.get("placement", "")
        mech_badge = _MECH_BADGE.get(mechanism, "⚪")
        cause_badge = _CAUSE_BADGE_MAP.get(cause_type, "")

        # Source category for clearer labeling
        cat = _source_category(source, mechanism)
        status = "" if retained else " ❌evicted"

        lines.append(f"\n  {mech_badge} [{cat}] {source} {cause_badge} {tokens}tok{status}")
        if placement:
            lines.append(f"     placement: {placement}")

        # Show actual content — up to 300 chars
        if content:
            preview = content[:300].replace("\n", "\n     ")
            if len(content) > 300:
                preview += "…"
            lines.append(f"     ───\n     {preview}")
        else:
            lines.append("     (no content captured)")

        total_tokens += tokens

    lines.append(f"\n  ── {len(cpr_parts)} parts · {total_tokens} tokens total")
    return "\n".join(lines)


def _stagger_coinc_processing_calls(seq: list[dict]) -> list[dict]:
    """Stagger coincident point-in-time ProcessingCall records with small offsets.

    When the runtime emits multiple per-actor ProcessingCall spans at the same
    wall-clock instant (start_ts == end_ts == ts_now), they would share the
    same StateNode boundaries and render as overlapping bars.  This helper
    gives each coincident ProcessingCall a tiny sequential offset so that each
    occupies its own visual slot in the Calls lane:

        PC1: (ts, ts+δ), PC2: (ts+δ, ts+2δ), …

    The stagger increment (1ms) is well below human perception but large
    enough to create distinct StateNode keys.
    """
    _STAGGER_DUR = 0.001  # 1ms per processing call
    if not seq:
        return seq
    result: list[dict] = []
    i = 0
    while i < len(seq):
        crec = seq[i]
        # Only stagger point-in-time ProcessingCalls (start ≈ end).
        if (
            crec.get("call_type") == "ProcessingCall"
            and abs(crec["end_ts"] - crec["start_ts"]) <= _TS_TOL
        ):
            ts    = crec["start_ts"]
            group: list[dict] = [crec]
            j     = i + 1
            while j < len(seq):
                nxt = seq[j]
                if (
                    nxt.get("call_type") == "ProcessingCall"
                    and abs(nxt["start_ts"] - ts) <= _TS_TOL
                    and abs(nxt["end_ts"]   - ts) <= _TS_TOL
                ):
                    group.append(nxt)
                    j += 1
                else:
                    break
            # Stagger each member with a small time offset.
            for idx, rec in enumerate(group):
                staggered = dict(rec)
                staggered["start_ts"] = ts + idx * _STAGGER_DUR
                staggered["end_ts"]   = ts + (idx + 1) * _STAGGER_DUR
                result.append(staggered)
            # Snap the next record's start_ts forward if it falls inside the
            # staggered group.  Only advance — never move it backward.
            _group_end = ts + len(group) * _STAGGER_DUR
            if j < len(seq):
                nxt_copy = dict(seq[j])
                if nxt_copy.get("start_ts", _group_end) < _group_end:
                    nxt_copy["start_ts"] = _group_end
                result.append(nxt_copy)
                i = j + 1
            else:
                i = j
        else:
            result.append(crec)
            i += 1
    return result
