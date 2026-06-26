#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Trajectory DAG validator — structural sanity checks on rendered lanes.

Imported by :func:`mas.lab.plots.multilevel_trajectory._build_dag` for
structural sanity checks on rendered trajectory lanes.

Usage
-----
::

    from mas.lab.plots._trajectory_validator import validate_trajectory_dag

    issues = validate_trajectory_dag(state_reg, lanes)
    for issue in issues:
        log.warning("[trajectory-validator] %s", issue)

Checks
------
1. **Strict alternation** — each lane sequence must be
   ``State, Trans, State, Trans, …, State`` (starts/ends with State).
2. **No consecutive transitions** — two TransNodes in a row without a
   StateNode between them (caught by rule 1, surfaced explicitly).
3. **No consecutive states** — two StateNodes without a TransNode between
   them (caught by rule 1, surfaced explicitly).
4. **LLM adjacency** — two LLMCall TransNodes separated only by a bare
   StateNode with no tool/processing call in between (warning; may indicate
   an orphan governance call that was not filtered).
5. **Timestamp ordering** — element timestamps must be non-decreasing within
   a lane (within ``_TS_TOL`` tolerance).
6. **Transition overlap** — two transitions in the same lane must not overlap
   in ``[start_ts, end_ts]``.
7. **Boundary consistency** — a TransNode's ``start_ts`` must be ≥ the
   preceding StateNode's ``ts``, and ``end_ts`` ≤ the following StateNode's
   ``ts``.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# 50 ms — same tolerance used by the plotter
_TS_TOL = 0.05


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryIssue:
    """A single structural problem detected in the DAG.

    Attributes
    ----------
    severity:
        ``"error"`` for invariants that will produce broken visuals, or
        ``"warning"`` for conditions that are unusual but may be intentional.
    message:
        Human-readable description of the problem.
    lane_id:
        Which lane the problem was found in (empty for cross-lane issues).
    ts:
        Reference timestamp near the problem site (0.0 if not applicable).
    """
    severity: str
    message:  str
    lane_id:  str   = ""
    ts:       float = 0.0

    def __str__(self) -> str:
        loc = f" [lane={self.lane_id}@{self.ts:.3f}s]" if self.lane_id else ""
        return f"[{self.severity.upper()}]{loc} {self.message}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def validate_trajectory_dag(
    state_reg: "dict[float, Any]",
    lanes:     "list[Any]",          # list[LaneDef]
) -> list[TrajectoryIssue]:
    """Run all structural checks on a built DAG.

    Parameters
    ----------
    state_reg:
        ``{ts: StateNode}`` registry produced by ``_build_dag``.
    lanes:
        Ordered list of ``LaneDef`` objects — each exposes a ``.sequence``
        of alternating ``StateNode`` / ``TransNode`` items and a
        ``.lane_id`` string.

    Returns
    -------
    list[TrajectoryIssue]
        All detected issues, empty if the DAG is structurally sound.
        Issues are **also** emitted as ``WARNING`` log messages so they
        appear in mas-lab run logs without raising.
    """
    issues: list[TrajectoryIssue] = []

    for lane in lanes:
        lid     = getattr(lane, "lane_id", "?")
        seq     = getattr(lane, "sequence", [])
        co_ts   = getattr(lane, "connector_only_ts", set())   # invisible dot states
        p_spans = getattr(lane, "parallel_spans", None)       # parallel agent groups
        _check_lane(lid, seq, issues, connector_only_ts=co_ts, parallel_spans=p_spans)

    _check_state_registry(state_reg, issues)

    for issue in issues:
        log.warning("[trajectory-validator] %s", issue)

    return issues


# ---------------------------------------------------------------------------
# Per-lane checks
# ---------------------------------------------------------------------------

def _check_lane(
    lane_id:           str,
    seq:               list,
    out:               list[TrajectoryIssue],
    connector_only_ts: "set[float] | None" = None,
    parallel_spans:    "list | None" = None,
) -> None:
    if not seq:
        return

    co_ts       = connector_only_ts or set()
    is_parallel = bool(parallel_spans)

    # Structural sequence for alternation checks: exclude connector_only
    # states (invisible dot nodes appended for cross-lane connector lines;
    # they are deliberately placed outside the alternating structure).
    structural = [
        el for el in seq
        if not (_elem_type(el) == "state" and _ts_of(el) in co_ts)
    ]
    types = [_elem_type(el) for el in structural]

    # ── 1. Must start and end with a State ──────────────────────────────
    if types[0] != "state":
        out.append(TrajectoryIssue(
            "error",
            f"sequence starts with '{types[0]}' instead of 'state'",
            lane_id=lane_id,
            ts=_ts_of(structural[0]),
        ))
    if types[-1] != "state":
        out.append(TrajectoryIssue(
            "error",
            f"sequence ends with '{types[-1]}' instead of 'state'",
            lane_id=lane_id,
            ts=_ts_of(structural[-1]),
        ))

    # ── 2+3. Consecutive same-class elements ────────────────────────────
    for i in range(len(types) - 1):
        if types[i] == types[i + 1] == "trans":
            ct_a = getattr(structural[i],     "call_type", "?")
            ct_b = getattr(structural[i + 1], "call_type", "?")
            out.append(TrajectoryIssue(
                "error",
                f"two consecutive transitions without a state between them"
                f" ({ct_a}@{_ts_of(structural[i]):.3f}s → {ct_b}@{_ts_of(structural[i+1]):.3f}s)",
                lane_id=lane_id,
                ts=_ts_of(structural[i]),
            ))
        elif types[i] == types[i + 1] == "state":
            out.append(TrajectoryIssue(
                "error",
                f"two consecutive states without a transition between them"
                f" (S@{_ts_of(structural[i]):.3f}s → S@{_ts_of(structural[i+1]):.3f}s)",
                lane_id=lane_id,
                ts=_ts_of(structural[i]),
            ))

    # ── 4. LLMCall adjacency ─────────────────────────────────────────────
    # Two LLMCalls separated only by a bare State (no tool/processing/agent
    # call between them) is physically impossible and signals a filtering bug.
    llm_idx = [
        i for i, el in enumerate(structural)
        if _elem_type(el) == "trans"
        and getattr(el, "call_type", "") == "LLMCall"
    ]
    for a, b in zip(llm_idx, llm_idx[1:]):
        between_types = [_elem_type(structural[j]) for j in range(a + 1, b)]
        has_non_state = any(t != "state" for t in between_types)
        if not has_non_state:
            out.append(TrajectoryIssue(
                "warning",
                f"two LLMCall transitions with only bare state(s) between them"
                f" (LLM@{_ts_of(structural[a]):.3f}s → LLM@{_ts_of(structural[b]):.3f}s)"
                " — possible orphan governance call not filtered",
                lane_id=lane_id,
                ts=_ts_of(structural[a]),
            ))

    # ── 5–7. Ordering, overlap, boundary — skip for parallel-content lanes ─
    # Lanes that participate in parallel groups (parallel_spans non-empty)
    # or contain calls from multiple parallel agents intentionally have
    # overlapping time ranges and non-monotonic timestamps.  These checks
    # would produce false positives for such lanes.
    agent_ids = {
        getattr(el, "agent_id", "") for el in seq if _elem_type(el) == "trans"
    }
    if is_parallel or len(agent_ids) > 1:
        return

    all_ts = [_ts_of(el) for el in structural]
    trans_sorted = sorted(
        [el for el in structural if _elem_type(el) == "trans"],
        key=lambda e: getattr(e, "start_ts", 0.0),
    )

    # ── 5. Timestamp ordering ────────────────────────────────────────────
    for i in range(len(all_ts) - 1):
        if all_ts[i + 1] < all_ts[i] - _TS_TOL:
            out.append(TrajectoryIssue(
                "warning",
                f"timestamps out of order"
                f" ({all_ts[i]:.3f}s → {all_ts[i+1]:.3f}s)",
                lane_id=lane_id,
                ts=all_ts[i],
            ))

    # ── 6. Transition overlap ────────────────────────────────────────────
    for a, b in zip(trans_sorted, trans_sorted[1:]):
        a_end   = getattr(a, "end_ts",   0.0)
        b_start = getattr(b, "start_ts", 0.0)
        if b_start < a_end - _TS_TOL:
            out.append(TrajectoryIssue(
                "warning",
                f"overlapping transitions"
                f" ({getattr(a,'call_type','?')} {getattr(a,'start_ts',0):.3f}–{a_end:.3f}s"
                f" ∩ {getattr(b,'call_type','?')} {b_start:.3f}–{getattr(b,'end_ts',0):.3f}s)",
                lane_id=lane_id,
                ts=getattr(a, "start_ts", 0.0),
            ))

    # ── 7. TransNode boundary vs surrounding StateNodes ──────────────────
    for i, el in enumerate(structural):
        if _elem_type(el) != "trans":
            continue
        prev_s = structural[i - 1] if i > 0 and _elem_type(structural[i - 1]) == "state" else None
        next_s = structural[i + 1] if i < len(structural) - 1 and _elem_type(structural[i + 1]) == "state" else None
        t_start = getattr(el, "start_ts", 0.0)
        t_end   = getattr(el, "end_ts",   0.0)
        ct      = getattr(el, "call_type", "?")
        if prev_s is not None:
            prev_ts = getattr(prev_s, "ts", 0.0)
            if t_start < prev_ts - _TS_TOL:
                out.append(TrajectoryIssue(
                    "warning",
                    f"transition '{ct}' starts before its preceding state"
                    f" (start={t_start:.3f}s < state.ts={prev_ts:.3f}s)",
                    lane_id=lane_id,
                    ts=t_start,
                ))
        if next_s is not None:
            next_ts = getattr(next_s, "ts", 0.0)
            if t_end > next_ts + _TS_TOL:
                out.append(TrajectoryIssue(
                    "warning",
                    f"transition '{ct}' ends after its following state"
                    f" (end={t_end:.3f}s > state.ts={next_ts:.3f}s)",
                    lane_id=lane_id,
                    ts=t_end,
                ))


# ---------------------------------------------------------------------------
# Cross-lane checks
# ---------------------------------------------------------------------------

def _check_state_registry(
    state_reg: "dict[float, Any]",
    out:       list[TrajectoryIssue],
) -> None:
    """Non-decreasing key order in the state registry."""
    ts_sorted = sorted(state_reg.keys())
    for a, b in zip(ts_sorted, ts_sorted[1:]):
        if b < a - _TS_TOL:
            out.append(TrajectoryIssue(
                "error",
                f"state registry keys out of order ({a:.3f}s → {b:.3f}s)",
            ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _elem_type(el: Any) -> str:
    """Classify an element as 'state', 'trans', or 'unknown' via duck typing."""
    # TransNode has call_type + start_ts/end_ts; StateNode has ts but not call_type
    if hasattr(el, "call_type"):
        return "trans"
    if hasattr(el, "ts"):
        return "state"
    return "unknown"


def _ts_of(el: Any) -> float:
    """Return the most representative timestamp for an element."""
    # StateNode → .ts; TransNode → .start_ts
    return float(
        getattr(el, "ts", None)
        or getattr(el, "start_ts", None)
        or 0.0
    )
