#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""DAG assembly: sequences → StateNode registry + LaneDef list."""

from collections import defaultdict
from typing import Optional

from mas.lab.plots._trajectory_validator import validate_trajectory_dag
from mas.lab.plots.multilevel_trajectory.annotations import (
    _HOVER_PRIORITY,
    _collect_annotations,
    _collect_context_provenance,
    _format_cpr_hover,
    _source_category,
    _stagger_coinc_processing_calls,
)
from mas.lab.plots.multilevel_trajectory.constants import (
    _PROC_TYPE_LABEL,
    _TS_TOL,
    TYPE_LABEL,
)
from mas.lab.plots.multilevel_trajectory.models import LaneDef, StateNode, TransNode
from mas.lab.plots.multilevel_trajectory.records import (
    _extract_final_output,
    _extract_user_input,
    _synthesize_thinking_records,
)
from mas.lab.plots.multilevel_trajectory.tree import (
    _align_record_boundaries,
    _build_call_tree,
    _make_agent_sequence,
    _make_call_sequence,
)

def _build_dag(
    records: list[dict],
    events:  list[dict],
    show_provenance: bool = True,
) -> tuple[dict[float, StateNode], list[LaneDef]]:
    """Assemble the DAG from the call tree.

    Returns
    -------
    state_reg : {ts: StateNode}     — shared state registry
    lanes     : [LaneDef, …]       — ordered swim-lane sequences

    Each lane's ``sequence`` is a strict alternation::

        [StateNode, TransNode, StateNode, TransNode, …, StateNode]

    States at the same ``ts`` in different lanes are the same object
    (shared reference), which the renderer uses to draw multi-lane connectors.
    """
    all_ts = [float(e.get("timestamp") or 0) for e in events if e.get("timestamp")]
    # Use record start/end times as the authoritative bounds — they include
    # synthetic end_ts (+1 s) for calls whose *_end event was missing,
    # which is always the correct diagram extent.  Raw event timestamps are
    # only a fallback when no records were produced.
    if records:
        t_min = min(r["start_ts"] for r in records)
        t_max = max(r["end_ts"]   for r in records)
    else:
        t_min = min(all_ts) if all_ts else 0.0
        t_max = max(all_ts) if all_ts else 1.0
    if t_max <= t_min:
        t_max = t_min + 1.0

    state_reg: dict[float, StateNode] = {}
    hover_pri: dict[float, int]       = {}

    # L2/L3 XAI annotation map: call_id → list of short summary strings
    ann_map: dict[str, list[str]] = _collect_annotations(events, records)

    # L4 context provenance: context_part_contributed → per-call_id summary
    cpr_map: dict[str, list[dict]] = (
        _collect_context_provenance(events, records) if show_provenance else {}
    )

    def state(ts: float, hover: str = "", level: str = "") -> StateNode:
        """Fetch or create the StateNode at *ts* (exact timestamp key).

        Hover text is overwritten only by a level with equal or higher
        priority (call > agent > mas > session).
        """
        pri = _HOVER_PRIORITY.get(level, -1)
        if ts not in state_reg:
            state_reg[ts] = StateNode(ts=ts, hover=hover)
            hover_pri[ts] = pri if hover else -1
        elif hover and pri >= hover_pri.get(ts, -1):
            state_reg[ts].hover = hover
            hover_pri[ts]       = pri
        return state_reg[ts]

    s_in  = _extract_user_input(events)
    s_out = _extract_final_output(events)
    entry = state(t_min, s_in,  "session")
    exit_ = state(t_max, s_out, "session")
    entry.is_user_entry = True
    exit_.is_user_exit  = True

    # Build call tree, align boundaries structurally, then derive sequences.
    children_of, parent_of = _build_call_tree(records)
    _align_record_boundaries(records, children_of)
    rec_by_id: dict[str, dict] = {r["call_id"]: r for r in records}
    mas_records    = sorted([r for r in records if r["level"] == "mas"],
                            key=lambda r: r["start_ts"])
    agent_sequence = _make_agent_sequence(records, children_of, parent_of)
    call_sequence  = _stagger_coinc_processing_calls(
        _make_call_sequence(agent_sequence, children_of)
    )

    seq_ctr = [0]

    def next_seq() -> int:
        seq_ctr[0] += 1
        return seq_ctr[0]

    def _provenance_block(rec: dict, ct: str) -> str:
        """Build a provenance triplet block for hover enrichment.

        Returns a compact multi-line string of ``(subject, predicate, object)``
        triplets that describe the structural graph context of the call.
        Empty string when nothing meaningful can be derived (e.g. Session).
        """
        lines: list[str] = []
        _cid = rec.get("call_id", "")
        _aid = rec.get("agent_id", "")

        # (call, type, CallType)
        lines.append(f"(call, type, {ct})")

        # (call, executedBy, agent)
        if _aid:
            lines.append(f"(call, executedBy, {_aid})")

        # (call, containedIn, parent)
        _pid = parent_of.get(_cid)
        if _pid:
            _prec = rec_by_id.get(_pid)
            if _prec:
                _pt = _prec.get("call_type", "?")
                _pa = _prec.get("agent_id") or _prec.get("label") or _pid[:12]
                lines.append(f"(call, containedIn, {_pa} [{_pt}])")

        # (call, usedModel, model) — LLMCall only
        _model = rec.get("model", "")
        if _model and ct in ("LLMCall", "MITMCall"):
            lines.append(f"(call, usedModel, {_model})")

        # (call, invoked, tool) — ToolCall only
        _tool = rec.get("tool_name", "")
        if _tool:
            lines.append(f"(call, invoked, {_tool})")

        # (call, children, N) — non-leaf calls
        _kids = children_of.get(_cid, [])
        if _kids:
            _child_types = defaultdict(int)
            for k in _kids:
                _child_types[k.get("call_type", "?")] += 1
            _parts = [f"{cnt}×{ctype}" for ctype, cnt in _child_types.items()]
            lines.append(f"(call, contains, {' '.join(_parts)})")

        if len(lines) <= 1:
            return ""
        return "\n\n🔗 Provenance:\n" + "\n".join(f"  {l}" for l in lines)

    def trans(
        rec: dict, *,
        lane_level: str,
        node_id: str,
        call_type: Optional[str] = None,
        label: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
    ) -> TransNode:
        ct  = call_type or rec.get("call_type", "AgentCall")
        lbl = label or rec.get("label") or TYPE_LABEL.get(ct, ct[:12])
        s   = start_ts if start_ts is not None else rec["start_ts"]
        e   = end_ts   if end_ts   is not None else (rec["end_ts"] or t_max)
        # Enrich hover_in with L2/L3 annotation summary (XAI)
        base_in  = rec.get("input", "")
        ann_lines = ann_map.get(rec.get("call_id", ""), [])
        hint     = ("\n\n[" + " | ".join(ann_lines) + "]") if ann_lines else ""
        # For LLMCall, prepend the call_id so it's visible in the hover panel.
        _cid = rec.get("call_id", "")
        _model = rec.get("model", "")
        call_id_prefix = ""
        if ct == "LLMCall" and _cid:
            _meta_parts = [f"call_id: {_cid}"]
            if _model:
                _meta_parts.append(f"model: {_model}")
            call_id_prefix = "📋 " + "  ·  ".join(_meta_parts) + "\n\n"
        _raw_out = rec.get("output", "")
        _thinking_txt = rec.get("thinking", "") if ct == "LLMCall" else ""
        if _thinking_txt:
            _hover_out = f"🧠 Thinking:\n\n{_thinking_txt}\n\n---\n\n{_raw_out}".strip()
        else:
            _hover_out = _raw_out
        # ProcessingCall: enrich hoverIn with the operation name header and
        # mark hoverOut as sentinel so JS can hide the useless "assembled" line.
        if ct == "ProcessingCall":
            _proc_name = rec.get("processing_name", "")
            # Detect fallback case: input == raw processing_type name (not real task)
            _is_type_name_fallback = base_in in _PROC_TYPE_LABEL
            _task_in = "(task content not captured in this trace)" if _is_type_name_fallback else base_in
            _op_header = f"[{_proc_name}]\n" if _proc_name else ""
            base_in    = (_op_header + _task_in).strip()
            # Clear output if it's just a status marker or a processing type name
            if _hover_out in ("", "assembled") or _hover_out in _PROC_TYPE_LABEL:
                _hover_out = ""
        # Build structured CPR data for rich JS rendering.
        # For ProcessingCall records that carry their own ``segments`` (per-actor
        # spans emitted by ObservabilityPlugin), build CPR from those segments
        # directly instead of from the cpr_map (which maps LLMCall call_ids).
        _rec_segments = rec.get("segments") if (show_provenance and ct == "ProcessingCall") else None
        if _rec_segments:
            _cpr_structured: list[dict] = []
            for _s in _rec_segments:
                _prov = _s.get("provenance") or {}
                _psrc = _s.get("source", "?")
                _pmech = _prov.get("mechanism", "inject")
                _entry: dict = {
                    "source": _psrc,
                    "category": _source_category(_psrc, _pmech),
                    "mechanism": _pmech,
                    "retrieval": _prov.get("retrieval", ""),
                    "decision": _prov.get("decision", ""),
                    "causeType": _prov.get("cause_type", "deterministic"),
                    "cause": _prov.get("cause", "?"),
                    "tokens": _s.get("tokens") or 0,
                    "retained": True,
                    "placement": _s.get("placement", ""),
                    "content": _s.get("content", ""),
                    "sourceType": _prov.get("source_type", ""),
                    "sourceId": _prov.get("source_id", ""),
                    "trigger": _prov.get("trigger", ""),
                    "actor": _prov.get("actor", ""),
                    "via": _prov.get("via", ""),
                }
                _ann = _prov.get("annotations")
                if _ann:
                    _entry["annotations"] = _ann
                _meta = _s.get("metadata")
                if _meta:
                    _entry["metadata"] = _meta
                _enrich = _prov.get("enrichments")
                if _enrich:
                    _entry["enrichments"] = _enrich
                _chain = _prov.get("chain")
                if _chain:
                    _entry["chain"] = _chain
                _cpr_structured.append(_entry)
            _cpr_raw = []  # no legacy CPR hover for per-actor spans
        else:
            _cpr_raw = cpr_map.get(_cid, [])
            _cpr_structured = []
            for _p in _cpr_raw:
                _psrc = _p.get("source", "?")
                _pmech = _p.get("access_mechanism", "inject")
                _entry: dict = {
                    "source": _psrc,
                    "category": _source_category(_psrc, _pmech),
                    "mechanism": _pmech,
                    "retrieval": _p.get("retrieval", ""),
                    "decision": _p.get("decision", ""),
                    "causeType": _p.get("cause_type", "deterministic"),
                    "cause": _p.get("cause", "?"),
                    "tokens": _p.get("token_estimate", 0),
                    "retained": _p.get("retained", True),
                    "placement": _p.get("placement", ""),
                    "content": _p.get("content", ""),
                    "sourceType": _p.get("source_type", ""),
                    "sourceId": _p.get("source_id", ""),
                    "trigger": _p.get("trigger", ""),
                    "actor": _p.get("actor", ""),
                    "via": _p.get("via", ""),
                }
                _ann = _p.get("annotations")
                if _ann:
                    _entry["annotations"] = _ann
                _meta = _p.get("metadata")
                if _meta:
                    _entry["metadata"] = _meta
                _enrich = _p.get("enrichments")
                if _enrich:
                    _entry["enrichments"] = _enrich
                _chain = _p.get("chain")
                if _chain:
                    _entry["chain"] = _chain
                _cpr_structured.append(_entry)
        return TransNode(
            node_id=node_id,
            call_type=ct,
            label=lbl,
            start_ts=s,
            end_ts=e,
            level=lane_level,
            agent_id=rec.get("agent_id", ""),
            seq=next_seq(),
            hover_in=(call_id_prefix + base_in + hint
                      + _format_cpr_hover(_cpr_raw)
                      + _provenance_block(rec, ct)).strip(),
            hover_out=_hover_out,
            is_instant=(ct not in ("AgentCall", "Session", "MASCall", "ProcessingCall") and abs(e - s) <= _TS_TOL),
            cpr_data=_cpr_structured,
            model=_model,
        )

    lanes: list[LaneDef] = []

    # ── Session lane: one wide transition covering the full session ──────────
    s0 = state(t_min, s_in,  "session")
    s1 = state(t_max, s_out, "session")
    sess_lane = LaneDef("session", "session", "Session")
    sess_lane.sequence = [
        s0,
        TransNode(
            node_id="tr-session",
            call_type="Session",
            label="Session",
            start_ts=s0.ts,
            end_ts=s1.ts,
            level="session",
            agent_id="",
            seq=next_seq(),
            hover_in=s_in,
            hover_out=s_out,
        ),
        s1,
    ]
    lanes.append(sess_lane)

    # ── MAS lane: one transition per MAS invocation, HITL gaps between them ──
    mas_lane = LaneDef("mas", "mas", "MAS")
    if mas_records:
        elems: list = [state(t_min, s_in, "session")]
        for i, mrec in enumerate(mas_records):
            end_ts = mrec["end_ts"] if mrec.get("end_ts", 0) > 0 else t_max
            elems.append(trans(mrec, lane_level="mas", node_id=f"tr-mas-{i}",
                               call_type="MASCall", label="MAS",
                               end_ts=end_ts))
            elems.append(state(end_ts, mrec.get("output", ""), "mas"))
            if i + 1 < len(mas_records):
                nxt = mas_records[i + 1]
                hitl_rec: dict = {"input": "", "output": "", "agent_id": ""}
                elems.append(trans(hitl_rec, lane_level="mas", node_id=f"tr-hitl-{i}",
                                   call_type="HITL", label="HITL",
                                   start_ts=end_ts, end_ts=nxt["start_ts"]))
                elems.append(state(nxt["start_ts"], "", "mas"))
        if not (isinstance(elems[-1], StateNode)
                and abs(elems[-1].ts - t_max) <= _TS_TOL):
            elems.append(state(t_max, s_out, "session"))
        mas_lane.sequence = elems
    else:
        empty: dict = {"input": s_in, "output": s_out, "agent_id": ""}
        mas_lane.sequence = [
            state(t_min),
            trans(empty, lane_level="mas", node_id="tr-mas-0",
                  call_type="MASCall", label="MAS",
                  start_ts=t_min, end_ts=t_max),
            state(t_max),
        ]
    lanes.append(mas_lane)

    # ── Agent lane: DFS-derived sequence, delegation splits included ─────────

    # Detect parallel agent groups: non-fragment records whose start_ts values
    # overlap (within _TS_TOL) share the same parallel fork/join span.  We
    # collect them into groups and assign a stable group id so the JS renderer
    # can display them side-by-side instead of sequentially.
    _parallel_info: dict[str, tuple[str, int, int]] = {}  # cid → (group_id, rank, size)
    _parallel_group_spans: list[dict] = []   # [{startTs, endTs, size}, …] for lane JSON
    _pg_counter = 0
    _active_pg: list[dict] = []             # accumulator for the current group
    _active_pg_end: float  = -1.0

    def _flush_parallel_group() -> None:
        nonlocal _pg_counter
        if len(_active_pg) > 1:
            _pg_counter += 1
            _gid = f"pg-{_pg_counter}"
            for _rank, _r in enumerate(_active_pg):
                _parallel_info[_r["call_id"]] = (_gid, _rank, len(_active_pg))
            _parallel_group_spans.append({
                "startTs": min(_r["start_ts"] for _r in _active_pg),
                "endTs":   max(_r["end_ts"]   for _r in _active_pg),
                "size":    len(_active_pg),
            })

    for _arec in agent_sequence:
        if _arec.get("_fragment"):
            _flush_parallel_group()
            _active_pg = []
            _active_pg_end = -1.0
            continue
        if not _active_pg:
            _active_pg     = [_arec]
            _active_pg_end = _arec["end_ts"]
        elif abs(_arec["start_ts"] - _active_pg[0]["start_ts"]) <= _TS_TOL:
            # Same-time start → parallel branch
            _active_pg.append(_arec)
            _active_pg_end = max(_active_pg_end, _arec["end_ts"])
        else:
            _flush_parallel_group()
            _active_pg     = [_arec]
            _active_pg_end = _arec["end_ts"]
    _flush_parallel_group()

    if agent_sequence:
        agent_lane = LaneDef("agents", "agent", "Agents")
        agent_lane.parallel_spans = _parallel_group_spans
        elems = [state(t_min, s_in, "session")]
        for i, arec in enumerate(agent_sequence):
            short  = arec["agent_id"].split(".")[-1][:18]
            end_ts = arec["end_ts"] if arec.get("end_ts", 0) > 0 else t_max
            _par   = _parallel_info.get(arec["call_id"])  # (group_id, rank, size) or None

            # Populate the START state of each agent fragment with its input so
            # delegation handoff boundaries show the task being passed in.
            # We do NOT append st_start: the previous fragment's st_end already
            # placed this state in the sequence (it's the same StateNode object).
            # For the first fragment, state(t_min) is pre-appended above.
            # Exception: for parallel agents with rank > 0, the previous element
            # in elems is the first branch's join state (at a later ts), so we
            # MUST explicitly insert the fork state to maintain sequence validity.
            st_start = state(arec["start_ts"], arec.get("input", ""), "agent")
            st_start.hover_by_lane["agents"] = arec.get("input", "")
            if _par:
                _gid, _rank, _size = _par
                if _rank == 0:
                    # Fork state: mark the boundary where parallel branches split.
                    # For rank 0 the fork state is already the previous iteration's
                    # st_end — just annotate it; never insert it again.
                    st_start.is_fork           = True
                    st_start.parallel_group_id = _gid
                    st_start.parallel_size     = _size
                # rank > 0: do NOT insert st_start into elems.
                # The JS parallel-slot renderer uses TransNode.startTs directly
                # (via agentParallelSlot) to position the bar — it does not need
                # a preceding StateNode anchor in the sequence.  Inserting one
                # for rank > 0 produces two consecutive StateNodes at slightly
                # different timestamps (the branches may start 1 ms apart),
                # causing the "S8 → S9" with no transition between them bug.

            _tr = trans(arec, lane_level="agent", node_id=f"tr-agent-{i}",
                        label=short, end_ts=end_ts)
            if _par:
                _gid, _rank, _size = _par
                _tr.parallel_group_id = _gid
                _tr.parallel_rank     = _rank
                _tr.parallel_size     = _size
            elems.append(_tr)
            _agent_output = arec.get("output", "")
            # Suppress bookkeeping strings that carry no semantic content.
            if _agent_output.startswith("Completed tool calls"):
                _agent_output = ""
            # Use "agent_end" level (priority 4 > call=3) so the agent's
            # returned output is the authoritative content for the state box
            # at this boundary — not a call-layer own_out/next_inp value.
            _end_level = "agent_end" if _agent_output else "agent"
            st_end = state(end_ts, _agent_output, _end_level)
            st_end.hover_by_lane["agents"] = _agent_output
            # Mark the state as interrupted only when the agent genuinely ran to
            # the trace cut-off (end_ts ≈ t_max).  Pre-delegation fragments of
            # the same parent record also carry _end_missing=True but have their
            # own explicit end_ts (child start), so they must NOT be flagged.
            if arec.get("_end_missing") and abs(end_ts - t_max) <= _TS_TOL:
                st_end.is_interrupted = True
            elif arec.get("_exec_status"):
                st_end.is_error = True
            if _par:
                _gid, _rank, _size = _par
                if _rank == _size - 1:
                    # Join state: last branch ends at the fork/join boundary
                    st_end.is_join           = True
                    st_end.parallel_group_id = _gid
                    st_end.parallel_size     = _size
            elems.append(st_end)
        if not (isinstance(elems[-1], StateNode)
                and abs(elems[-1].ts - t_max) <= _TS_TOL):
            elems.append(state(t_max, s_out, "session"))
        agent_lane.sequence = elems
        lanes.append(agent_lane)

    # ── Call lane: direct call children of each agent fragment ───────────────
    if call_sequence:
        call_lane = LaneDef("calls", "call", "Calls")
        elems = [state(t_min, s_in, "session")]
        for j, crec in enumerate(call_sequence):
            ct_j   = crec.get("call_type", "")
            end_ts = crec["end_ts"] if crec.get("end_ts", 0) > 0 else t_max
            # Every call type (including ProcessingCall) gets its own state pair.
            # ProcessingCall is now a real bar so the prompt-assembly step is
            # visible as a distinct chain node (S_k → ⚙prompt → S_{k+1} → llm → …).
            # Truly instant calls (ToolCall/MemoryCall/RAGQuery with duration≈0)
            # use is_instant=True and are rendered as icon badges by the HTML renderer.
            st_start = state(crec["start_ts"], crec.get("input", ""), "call")
            st_start.hover_by_lane["calls"] = crec.get("input", "")
            _tr = trans(crec, lane_level="call", node_id=f"tr-call-{j}",
                        end_ts=end_ts)
            # Context provenance (the "N parts · M tokens · System Prompt ×… ,
            # Context ×…" breakdown) describes the *assembled context* — a state,
            # not the LLM action.  Attach it to the LLM's start state (the node
            # between ⚙ context and the LLM bar) and leave the LLM bar to
            # represent the call itself.
            if ct_j == "LLMCall" and _tr.cpr_data:
                if not st_start.cpr_data:
                    st_start.cpr_data = _tr.cpr_data
                    st_start.model = _tr.model
                _tr.cpr_data = []
            elems.append(_tr)
            own_out  = crec.get("output", "")
            # ProcessingCall outputs are operation summaries ("3 injections · 51
            # tok") — they belong on the transition bar, not on the following
            # state.  Clear them so the state can show cumulative context instead.
            if ct_j == "ProcessingCall":
                own_out = ""
            next_rec  = call_sequence[j + 1] if j + 1 < len(call_sequence) else None
            next_inp  = next_rec.get("input", "") if next_rec else ""
            end_hover = own_out or next_inp
            # A tool-turn LLM call emits no text (the model returned a tool
            # call, captured as the next bar), so its end state would be empty.
            # Show what the call led to instead of a bare "(no content)".
            if not end_hover and next_rec:
                _nl = next_rec.get("label") or _PROC_TYPE_LABEL.get(
                    next_rec.get("call_type", ""), next_rec.get("call_type", "")
                )
                if _nl:
                    end_hover = f"→ {_nl}"
            st_end = state(end_ts, end_hover, "call")
            st_end.hover_by_lane["calls"] = end_hover
            elems.append(st_end)

        # ── Propagate the context breakdown to EVERY state ──────────────
        # Each state is the working memory at that instant.  Every action's
        # result enters working memory (appended to the end of context for
        # visualization), so the assembled context grows monotonically along the
        # lane.  Each LLM call's context snapshot already sits on its start state
        # (see the CPR move above); carry the latest snapshot forward to the
        # states that follow it, and back-fill the states before the first
        # snapshot with that first one, so no state is left without a breakdown.
        _model_for_states: str = ""
        for el in elems:
            if isinstance(el, TransNode) and el.call_type == "LLMCall" and el.model:
                _model_for_states = el.model
                break
        _latest_cpr: list[dict] = []
        for el in elems:
            if isinstance(el, StateNode):
                if el.cpr_data:
                    _latest_cpr = el.cpr_data
                elif _latest_cpr:
                    el.cpr_data = list(_latest_cpr)
                    if not el.model:
                        el.model = _model_for_states
        # Back-fill leading states (before the first snapshot).
        _first_cpr: list[dict] = next(
            (el.cpr_data for el in elems if isinstance(el, StateNode) and el.cpr_data),
            [],
        )
        if _first_cpr:
            for el in elems:
                if isinstance(el, StateNode):
                    if el.cpr_data:
                        break
                    el.cpr_data = list(_first_cpr)
                    if not el.model:
                        el.model = _model_for_states

        call_lane.sequence = elems
        lanes.append(call_lane)

        # Inject agent-boundary timestamps that are not yet present in the call
        # lane.  This ensures delegation splits and fragment boundaries are
        # visible in the Calls lane and that cross-lane connector lines appear
        # at every shared state (not just call-end timestamps).
        call_ts: set[float] = {el.ts for el in elems if isinstance(el, StateNode)}
        for arec in agent_sequence:
            for bts in (arec["start_ts"], arec["end_ts"]):
                # Skip if a call state already sits at (or within a hair of) this
                # boundary.  Agent execution boundaries can fall a millisecond off
                # the nearest call boundary (e.g. execution_end fires just before
                # the final llm_call_end); injecting a near-duplicate state there
                # creates an empty connector column between two states with no
                # transition (the "S9 → S10 with nothing between" glitch).
                if any(abs(bts - ex) <= _TS_TOL for ex in call_ts):
                    continue
                injected = state(bts)
                call_lane.connector_only_ts.add(bts)
                call_lane.sequence.append(injected)
                call_ts.add(bts)

    # ── Thinking lane: one ThinkingCall per LLM call that has thinking content
    thinking_records = _synthesize_thinking_records(records)
    thinking_sub_tss: list[float] = []   # intermediate state ts values (for letter labels)

    # Build a map from LLM call_id → staggered start_ts so the thinking lane
    # anchors at the correct (post-stagger) timestamp.
    _staggered_llm_starts: dict[str, float] = {
        r["call_id"]: r["start_ts"]
        for r in call_sequence
        if r.get("call_type") == "LLMCall"
    }

    if thinking_records:
        thinking_lane = LaneDef("thinking", "thinking", "Thinking")
        telems: list = []
        prev_ts: float | None = None
        prev_agent_id: str | None = None

        for k, trec in enumerate(sorted(thinking_records, key=lambda r: r["start_ts"])):
            # Use staggered LLM call start_ts (parent_call_id points to the
            # LLMCall) so the thinking lane aligns with the call lane visually.
            _parent_cid = trec.get("parent_call_id", "")
            ts_start = _staggered_llm_starts.get(_parent_cid, trec["start_ts"])
            # Adjust thinking end proportionally to the staggered start.
            _orig_start = trec["start_ts"]
            _offset = ts_start - _orig_start
            ts_think_end = (trec["end_ts"] if trec.get("end_ts", 0) > 0 else t_max) + _offset
            ts_llm_end   = (trec.get("_llm_end_ts") or t_max)

            if prev_ts is None:
                # First thinking record — lane anchors at the LLM call (ts_start)
                _st_anchor = state(ts_start, trec.get("input", ""), "call")
                _st_anchor.hover_by_lane["thinking"] = trec.get("input", "")
                telems.append(_st_anchor)
            elif ts_start > prev_ts + _TS_TOL:
                _is_inter_agent = (prev_agent_id is not None and prev_agent_id != trec["agent_id"])
                # Add the anchor state; mark as laneRestart when agents differ
                # (breaks lifeline — thinking is per-agent, not continuous).
                # For same-agent gaps the lifeline connects them naturally.
                _st_gap_end = state(ts_start, trec.get("input", ""), "call")
                _st_gap_end.hover_by_lane["thinking"] = trec.get("input", "")
                if _is_inter_agent:
                    _st_gap_end.is_lane_restart = True
                telems.append(_st_gap_end)
            else:
                # The boundary state at ts_start already exists in state_reg
                # (registered by the call lane). Update its thinking hover and
                # append it to telems so the thinking lane renders a box there.
                _anch = state(ts_start)
                _anch.hover_by_lane["thinking"] = trec.get("input", "")
                telems.append(_anch)

            # ThinkingCall transition: from LLM call start → thinking end (85%)
            telems.append(trans(trec, lane_level="thinking",
                                node_id=f"tr-think-{k}",
                                call_type="ThinkingCall", label="Think",
                                start_ts=ts_start, end_ts=ts_think_end))
            think_st = state(ts_think_end, trec.get("output", ""), "thinking")
            think_st.hover_by_lane["thinking"] = trec.get("output", "")
            telems.append(think_st)
            thinking_sub_tss.append(ts_think_end)   # mark as letter-suffix candidate

            # Output passthrough: thinking end → LLM call end (remaining 15%)
            # Rendered as ThinkingEmit (indigo-900, label "Emit") so users can
            # distinguish it from the idle gap before thinking starts.
            if ts_llm_end > ts_think_end + _TS_TOL:
                emit_rec: dict = {"input": trec.get("output", ""), "output": trec.get("llm_output", ""), "agent_id": trec["agent_id"]}
                telems.append(trans(emit_rec, lane_level="thinking",
                                    node_id=f"tr-think-out-{k}",
                                    call_type="ThinkingEmit", label="Emit",
                                    start_ts=ts_think_end, end_ts=ts_llm_end))
                telems.append(state(ts_llm_end))
                prev_ts = ts_llm_end
            else:
                prev_ts = ts_think_end
            prev_agent_id = trec["agent_id"]

        # Lane ends at the state after the last Emit — no leading gap from t_min,
        # no trailing gap to t_max.

        thinking_lane.sequence = telems
        lanes.append(thinking_lane)

    # ── Assign letter-suffix labels to thinking sub-states (S2 → S2a, S2b …)
    if thinking_sub_tss:
        from collections import defaultdict as _defdict
        all_bkts_tmp = sorted(state_reg.keys())
        _state_num_tmp = {b: i + 1 for i, b in enumerate(all_bkts_tmp)}
        # Group sub-states by their preceding numbered state
        _pred_to_subs: dict[int, list[float]] = _defdict(list)
        for _ts in sorted(thinking_sub_tss):
            _preds = [b for b in all_bkts_tmp if b < _ts - _TS_TOL]
            if _preds:
                _pn = _state_num_tmp[max(_preds)]
                _pred_to_subs[_pn].append(_ts)
        for _pn, _subs in _pred_to_subs.items():
            for _idx, _ts in enumerate(sorted(_subs)):
                state_reg[_ts].label_override = f"S{_pn}{chr(ord('a') + _idx)}"

    # ── Reassign sequential IDs globally (chronological, level as tiebreaker)
    _LEVEL_ORDER = {"session": 0, "mas": 1, "agent": 2, "call": 3, "thinking": 4}
    all_trans = [el for lane in lanes for el in lane.sequence
                 if isinstance(el, TransNode)]
    all_trans.sort(key=lambda t: (t.start_ts, _LEVEL_ORDER.get(t.level, 9)))
    for i, t in enumerate(all_trans):
        t.seq = i + 1

    # ── Structural sanity check ──────────────────────────────────────────
    validate_trajectory_dag(state_reg, lanes)

    return state_reg, lanes
