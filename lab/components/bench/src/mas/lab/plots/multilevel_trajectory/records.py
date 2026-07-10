#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Event parsing: events → typed execution records."""

import json
from collections import defaultdict
from typing import Any

from mas.lab.plots.multilevel_trajectory.constants import (
    _CALL_TYPE_TO_LEVEL,
    _KIND_BASE_TO_TYPE,
    _PROC_TYPE_LABEL,
    _TS_TOL,
)

def _build_call_records(events: list[dict]) -> list[dict]:
    """Pair ``*_start`` / ``*_end`` events into typed execution record dicts.

    Each record has the keys::

        call_id, parent_call_id, call_type, level, agent_id,
        start_ts, end_ts, input, output, label, tool_name, model

    When the runtime emits ``call_id`` / ``parent_call_id`` on the event
    (observability_plugin ≥ v2), those values are used verbatim.  Older
    traces that lack these fields fall back to synthetic ids so that
    ``_build_call_tree`` can still use its timestamp-containment path.
    """
    records: list[dict] = []
    open_calls: dict[tuple, list[dict]] = defaultdict(list)
    call_seq:   dict[tuple, int]        = defaultdict(int)
    # The native observability layer emits each engine op (LLM/tool/memory)
    # twice (~1ms apart: the operator wrapper + the engine adapter). Without
    # dedup, records.py builds two overlapping records per call, which corrupts
    # boundary alignment (a ToolCall inherits a later duplicate's end_ts and
    # overlaps the following LLM, so the renderer drops the tool bar). Dedup by
    # (correlation_id, kind) keeps the first start/end of each engine op.
    _seen_engine_io: set[tuple] = set()
    _ENGINE_IO_TYPES = {"LLMCall", "ToolCall", "MemoryCall", "RAGQuery"}

    # The native llm_call_start boundary carries no prompt (the engine builds
    # messages internally). The assembled prompt is emitted on the
    # context_assembled event with the same correlation_id — map it here so the
    # LLM record can show the prompt. (Order-independent: context_assembled may
    # be emitted after its llm_call_start.)
    _ca_messages_by_corr: dict[Any, list] = {}
    for _e in events:
        if _e.get("kind") == "context_assembled" and _e.get("messages"):
            _c = _e.get("correlation_id")
            if _c is not None:
                _ca_messages_by_corr.setdefault(_c, _e["messages"])

    # A tool call is emitted twice under the same call_id: once by the generic
    # envelope-activity wrapper (tool_name "contract_call") and once by the
    # engine-io boundary carrying the real tool name (lookup_schedule,
    # get_fares, delegate_to_<id>, …).  Map each call_id to its specific name so
    # records show the real tool rather than the generic wrapper.
    _GENERIC_TOOL_NAMES = {"contract_call", ""}
    _tool_name_by_call: dict[str, str] = {}
    _tool_args_by_call: dict[str, Any] = {}
    for _e in events:
        if "tool_call" not in (_e.get("kind") or ""):
            continue
        _cid2 = _e.get("call_id")
        if not _cid2:
            continue
        _tn2 = _e.get("tool_name") or ""
        if _tn2 not in _GENERIC_TOOL_NAMES:
            _tool_name_by_call.setdefault(_cid2, _tn2)
        # The real arguments ride on the engine-io emission, not the generic
        # envelope wrapper — capture them so the tool bar shows its call args.
        _args2 = _e.get("arguments")
        if _cid2 not in _tool_args_by_call and isinstance(_args2, dict) and _args2:
            _tool_args_by_call[_cid2] = _args2

    for ev in sorted(events, key=lambda e: float(e.get("timestamp") or 0)):
        kind      = ev.get("kind", "")
        kind_base = kind.replace("_start", "").replace("_end", "")
        agent_id  = ev.get("agent_id", "")
        tool_name = ev.get("tool_name", "")
        # Resolve generic "contract_call" wrappers to the real tool name so the
        # start/end pair on a consistent key and the bar shows the true tool.
        if "tool_call" in kind and tool_name in _GENERIC_TOOL_NAMES:
            _rn = _tool_name_by_call.get(ev.get("call_id") or "")
            if _rn:
                tool_name = _rn
                ev = {**ev, "tool_name": _rn}  # so _build_call_label sees it too
        call_type = _KIND_BASE_TO_TYPE.get(kind_base)
        if call_type is None:
            continue
        # Drop duplicate engine-op emissions (see _seen_engine_io above).
        # Key on agent_id too: correlation_id restarts per agent, so a peer's
        # LLM (corr=1) must not be mistaken for the entry agent's LLM (corr=1)
        # in a multi-agent run — that would delete the peer's calls entirely.
        if call_type in _ENGINE_IO_TYPES:
            _corr = ev.get("correlation_id")
            if _corr is not None:
                _io_key = (agent_id, _corr, kind_base, kind.endswith("_end"))
                if _io_key in _seen_engine_io:
                    continue
                _seen_engine_io.add(_io_key)
        # Skip self-referential start events: these are inner-layer duplicate
        # emissions where the engine adapter reuses the same call_id that the
        # ObservabilityOperator wrapper already pushed as a frame.
        # Symptom: parent_call_id == call_id (a call cannot be its own parent).
        # Keeping both would produce two records with the same call_id — the
        # inner (orphaned) record's end_ts defaults to start + 1.0 s and
        # causes boundary-alignment to corrupt unrelated records' timestamps.
        if kind.endswith("_start"):
            _cid = ev.get("call_id")
            _pid = ev.get("parent_call_id")
            if _cid and _pid and _cid == _pid:
                continue
        # Promote MITM processing calls to a dedicated visual type.
        if call_type == "ProcessingCall" and ev.get("processing_type") == "mitm_rewrite":
            call_type = "MITMCall"
        key = (agent_id, kind_base, tool_name)

        # Attach the assembled prompt to LLM starts that lack inline messages.
        if kind.endswith("_start") and call_type == "LLMCall" and not ev.get("messages"):
            _mc = _ca_messages_by_corr.get(ev.get("correlation_id"))
            if _mc:
                ev = {**ev, "messages": _mc}

        if kind.endswith("_start"):
            seq = call_seq[key]
            call_seq[key] += 1
            record: dict[str, Any] = {
                "call_id":        ev.get("call_id") or f"{kind_base}-{agent_id}-{seq}",
                "parent_call_id": ev.get("parent_call_id"),  # None for roots / old traces
                "_has_ids":  "call_id" in ev,  # True when runtime emitted the field
                "call_type": call_type,
                "level":     _CALL_TYPE_TO_LEVEL.get(call_type, "call"),
                "agent_id":  agent_id,
                "start_ts":  float(ev.get("timestamp") or 0),
                "end_ts":    0.0,
                "input":     ev.get("input") or ev.get("prompt") or "",
                "output":    "",
                "label":     _build_call_label(call_type, ev),
                "tool_name": tool_name,
                "model":     ev.get("model", ""),
                "thinking":  "",
                "correlation_id": ev.get("correlation_id"),
                "processing_name": ev.get("processing_name", "") if call_type == "ProcessingCall" else "",
            }
            # Preserve per-actor context segments from ProcessingCall events
            # so the trajectory card can build CPR data directly.
            if call_type == "ProcessingCall" and ev.get("segments"):
                record["segments"] = ev["segments"]
            if call_type == "LLMCall" and ev.get("messages"):
                msgs = ev["messages"]
                if isinstance(msgs, list) and msgs:
                    # The LLM input is the *full assembled context* actually sent
                    # to the model — the system prompt concatenated with the user
                    # turn (and, on follow-up calls, the conversation history and
                    # tool / sub-agent results).  This is the output of the
                    # preceding ⚙ context node, shown on the state between it and
                    # the LLM bar.  The user-entry state (S1) keeps the bare user
                    # question; the system prompt only appears here, post-assembly.
                    lines: list[str] = []
                    for m in msgs:
                        role = m.get("role", "?")
                        content = m.get("content") or ""
                        if isinstance(content, list):
                            content = " ".join(
                                p.get("text", "") for p in content if isinstance(p, dict)
                            )
                        if not content:
                            continue
                        _label = "TOOL RESULT" if role == "tool" else role.upper()
                        lines.append(f"[{_label}]\n{str(content)}")
                    if lines:
                        record["input"] = "\n\n---\n\n".join(lines)
            if call_type == "ToolCall" and not record["input"]:
                # tool_call_start stores params in 'arguments', not 'input'.
                # Resolve from the engine-io emission (the generic envelope
                # wrapper carries no arguments) so the bar shows the real args.
                raw_args = ev.get("arguments") or _tool_args_by_call.get(ev.get("call_id") or "")
                if raw_args is not None and str(raw_args).strip() not in ("", "None", "null", "{}"):
                    _tn = ev.get("tool_name") or tool_name or "tool"
                    if isinstance(raw_args, dict):
                        _argstr = ", ".join(f"{k}={v!r}" for k, v in raw_args.items())
                    else:
                        _argstr = str(raw_args)
                    record["input"] = f"→ {_tn}({_argstr})"
                else:
                    # At minimum show which tool is being called
                    record["input"] = f"→ {ev.get('tool_name') or tool_name or 'tool'}()"
            if call_type == "ProcessingCall" and not record["input"]:
                # Fallback: reconstruct a readable summary from the extra fields
                # emitted by the runtime (sections, evicted_sections, etc.).
                _pt = ev.get("processing_type", "")
                if _pt == "memory_injection":
                    _n = len(ev.get("sections") or [])
                    _t = ev.get("tokens") or 0
                    record["input"] = f"{_n} section{'s' if _n != 1 else ''} · {_t} tok"
                elif _pt == "ontology_injection":
                    _n = len(ev.get("sections") or [])
                    record["input"] = f"{_n} section{'s' if _n != 1 else ''}"
                elif _pt == "context_compression":
                    _n = len(ev.get("evicted_sections") or [])
                    _t = ev.get("evicted_tokens") or 0
                    record["input"] = f"{_n} evicted · {_t} tok"
                elif _pt == "context_paging":
                    _n = ev.get("summarized_turns") or 0
                    record["input"] = f"{_n} turn{'s' if _n != 1 else ''} summarized"
                elif _pt:
                    record["input"] = _pt
            if call_type == "ContextState":
                action = str(ev.get("update_type") or "mutation")
                turn = ev.get("turn_index")
                wm = ev.get("wm_count")
                committed = ev.get("committed_count")
                record["update_type"] = action
                record["input"] = (
                    f"{action}"
                    + (f" · turn {turn}" if turn is not None else "")
                    + (f" · wm={wm}" if wm is not None else "")
                    + (f" · hist={committed}" if committed is not None else "")
                )
            open_calls[key].append(record)

        elif kind.endswith("_end") and open_calls[key]:
            # Match by call_id when the runtime emitted it on the end event
            # (avoids wrong pairing for nested same-type calls, e.g. a tool
            # wrapping sub-tool-calls that all share the same key).
            # Fallback: FIFO (older traces that omit call_id on _end events).
            _end_cid = ev.get("call_id")
            record = None
            if _end_cid:
                for _ix, _r in enumerate(open_calls[key]):
                    if _r.get("call_id") == _end_cid:
                        record = open_calls[key].pop(_ix)
                        break
            if record is None:
                record = open_calls[key].pop(0)
            record["end_ts"] = float(ev.get("timestamp") or 0)
            _ex_status = ev.get("status") or "success"
            if _ex_status not in ("success", "ok", ""):
                record["_exec_status"] = _ex_status
            out = ev.get("output") or ev.get("result") or ""
            if call_type == "LLMCall":
                _thinking = ev.get("thinking") or (ev.get("response") or {}).get("thinking") or ""
                if _thinking:
                    record["thinking"] = _thinking
                resp = ev.get("response") or {}
                if isinstance(resp, dict):
                    # Support both formats:
                    #   canonical OpenAI: choices[0].message.{content, tool_calls}
                    #   flat runtime:     {content, tool_calls, usage}
                    choices = resp.get("choices") or []
                    if choices:
                        msg        = choices[0].get("message") or {}
                        content    = msg.get("content") or ""
                        tool_calls = msg.get("tool_calls") or []
                    else:
                        content    = str(resp.get("content") or "")
                        tool_calls = resp.get("tool_calls") or []

                    parts: list[str] = []
                    if content:
                        parts.append(content)
                    if tool_calls:
                        tc_lines: list[str] = []
                        for tc in tool_calls:
                            fn   = tc.get("function") or {}
                            name = fn.get("name") or tc.get("name") or "?"
                            args = fn.get("arguments") or tc.get("arguments") or ""
                            if not isinstance(args, str):
                                args = json.dumps(args, ensure_ascii=False)
                            tc_lines.append(f"[Tool call] → {name}({args})")
                        parts.append("\n".join(tc_lines))
                    if parts:
                        out = "\n\n".join(parts)
            out_str = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
            record["output"] = out_str
            # Fallback: ProcessingCall output from processing_output field (end event)
            if call_type == "ProcessingCall" and not record["output"]:
                record["output"] = ev.get("processing_output") or record.get("input", "")
            if call_type == "ContextState" and not record["output"]:
                record["output"] = str(ev.get("content_preview") or ev.get("output") or "")
            records.append(record)

    # Close any records whose _end event was missing.
    for pending_list in open_calls.values():
        for rec in pending_list:
            if rec.get("end_ts", 0) <= 0:
                rec["end_ts"] = rec["start_ts"] + 1.0
                rec["_end_missing"] = True
            # Ensure parent_call_id key is always present (may be None for roots).
            rec.setdefault("parent_call_id", None)
        records.extend(pending_list)

    # Drop orphaned engine-op duplicates.  The native layer can emit an engine op
    # (tool/memory/rag) twice under different correlation ids; when only one gets
    # an ``*_end`` event, the other is left ``_end_missing`` and — lacking a real
    # end — balloons across the whole execution during boundary alignment,
    # overlapping the twin that actually completed (two ``lookup_schedule`` bars,
    # one instant and one multi-second).  When an ``_end_missing`` engine-io
    # record has a completed twin (same agent + tool, start within tolerance) it
    # is a real parallel call whose end the trace omitted.
    _ENGINE_IO_CT = {"ToolCall", "MemoryCall", "RAGQuery"}
    _completed_io = [
        r for r in records
        if r.get("call_type") in _ENGINE_IO_CT and not r.get("_end_missing")
    ]
    if _completed_io:
        # A model can fire the *same* tool twice in parallel (one assistant
        # message, two tool_calls → two results).  The native layer sometimes
        # emits the second call's start but not its *_end, leaving it
        # ``_end_missing`` so boundary alignment balloons it across the whole
        # execution.  These are real parallel calls (distinct call ids), NOT
        # duplicates — keep them: give each the completed twin's end so it renders
        # as its own bar, and re-home any children (a follow-up LLM that inherited
        # the orphan as parent) onto the orphan's parent so they are not nested
        # under a tool.
        _twin_end: dict = {}
        _orphan_parent: dict = {}
        for r in records:
            if r.get("_end_missing") and r.get("call_type") in _ENGINE_IO_CT:
                twin = next(
                    (c for c in _completed_io
                     if c is not r
                     and c.get("agent_id") == r.get("agent_id")
                     and c.get("tool_name") == r.get("tool_name")
                     and abs(c["start_ts"] - r["start_ts"]) <= _TS_TOL),
                    None,
                )
                if twin is not None:
                    _twin_end[r["call_id"]] = twin["end_ts"]
                    _orphan_parent[r["call_id"]] = r.get("parent_call_id")
        if _twin_end:
            for r in records:
                if r["call_id"] in _twin_end:
                    r["end_ts"] = _twin_end[r["call_id"]]
                    r.pop("_end_missing", None)
                _p = r.get("parent_call_id")
                while _p in _orphan_parent:
                    _p = _orphan_parent[_p]
                if _p != r.get("parent_call_id"):
                    r["parent_call_id"] = _p

    # Re-parent "impossible" children whose start_ts is at/after their parent's
    # real end_ts.  A call that begins after its parent already returned cannot
    # truly be nested under it — it is a sibling.  This happens when the runtime
    # observability call-stack does not pop a completed engine-op frame (e.g. a
    # tool call) before the next op fires, so a follow-up LLM inherits the tool
    # as its parent.  Left uncorrected, _align_record_boundaries stretches the
    # parent to contain the mis-attached child, which overlaps the real sibling
    # and drops its bar from the render.  Walking up to the grandparent is safe
    # for genuine delegation: there the sub-agent starts *during* the wrapping
    # tool (start < parent.end), so it is never reparented.
    _rp_by_id = {r["call_id"]: r for r in records}
    for r in records:
        _pid = r.get("parent_call_id")
        _parent = _rp_by_id.get(_pid) if _pid else None
        while (
            _parent is not None
            and _parent is not r
            and _parent.get("end_ts", 0) > 0
            and not _parent.get("_end_missing")
            and r["start_ts"] >= _parent["end_ts"] - _TS_TOL
        ):
            _pid = _parent.get("parent_call_id")
            r["parent_call_id"] = _pid
            _parent = _rp_by_id.get(_pid) if _pid else None

    # Link delegated sub-agent executions under the tool call that spawned them
    # so the Agent lane interleaves them sequentially (moderator → schedule_agent
    # → moderator …).  A delegation runs the peer's turn inside the delegating
    # agent's tool call (``delegate_to_<id>`` / ``contract_call``); the peer
    # emits its own execution record but, arriving through the peer bus, parents
    # to the MAS call.  Re-link structurally: a peer execution (different agent)
    # whose whole span is contained within a ToolCall of another agent is that
    # tool's delegated child.  This is unambiguous — a foreign agent running
    # inside another agent's tool window is a delegation — and needs no tool-name
    # heuristic.  _make_agent_sequence then splits the delegator into fragments.
    _agent_execs = [r for r in records if r.get("level") == "agent"]
    _tool_calls = [r for r in records if r.get("call_type") == "ToolCall"]
    for _peer in _agent_execs:
        _best = None
        for _tool in _tool_calls:
            if _tool.get("agent_id") == _peer.get("agent_id"):
                continue  # a tool cannot delegate to its own agent
            if (_peer["start_ts"] >= _tool["start_ts"] - _TS_TOL
                    and _peer["end_ts"] <= _tool["end_ts"] + _TS_TOL):
                # Tightest containing tool wins (handles nested delegations).
                if _best is None or (_tool["end_ts"] - _tool["start_ts"]) < (
                        _best["end_ts"] - _best["start_ts"]):
                    _best = _tool
        if _best is not None:
            _peer["parent_call_id"] = _best["call_id"]

    # Fix synthetic end_ts for governance-orphaned LLMCalls.
    # When governance fires between two llm_call_start events, the first call
    # never receives an llm_call_end and gets the placeholder end_ts of
    # start_ts + 1.0.  Replace that with the start_ts of the chronologically
    # next sibling LLMCall so that the orphan's duration is accurate (≈ the
    # time until governance handed off to the next call) and child records
    # (e.g. memory_search ToolCalls nested under the orphan) don't get their
    # boundaries inflated by _align_record_boundaries Rule 3.
    _by_parent: dict[Any, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("call_type") == "LLMCall":
            _by_parent[r.get("parent_call_id")].append(r)
    for _siblings in _by_parent.values():
        if len(_siblings) < 2:
            continue
        _llm_sorted = sorted(_siblings, key=lambda r: r["start_ts"])
        for _idx, _llm in enumerate(_llm_sorted):
            if not _llm.get("_end_missing"):
                continue
            # Find the next sibling that starts strictly after this one.
            # Use a 1 ms tolerance (not _TS_TOL=50 ms) so that even rapid
            # governance short-circuits (< 50 ms) get their end_ts fixed.
            for _j in range(_idx + 1, len(_llm_sorted)):
                _nxt = _llm_sorted[_j]
                if _nxt["start_ts"] > _llm["start_ts"] + 0.001:
                    _llm["end_ts"] = _nxt["start_ts"]
                    break

    # Agent records that never received an execution_end event were still
    # executing when the trace was cut.  Using start_ts + 1.0 as their end
    # would truncate their call window and cause call-lane children to be
    # silently dropped by the _collect window filter.  Instead, extend them
    # to t_final — the last known timestamp in the trace — which is the
    # structurally correct boundary: "running until end of observation".
    _t_final = max((r["end_ts"] for r in records), default=0.0)
    for rec in records:
        if rec.get("_end_missing") and rec.get("level") == "agent":
            rec["end_ts"] = _t_final

    # Multiple agents may share the same runtime call_id (e.g. u1-exec); ensure
    # agent-lane records remain uniquely addressable in the call tree.
    _seen_ids: set[str] = set()
    for rec in records:
        cid = str(rec.get("call_id") or "")
        if not cid:
            continue
        if cid in _seen_ids and rec.get("level") == "agent":
            rec["call_id"] = f"{cid}-{rec.get('agent_id', 'agent')}"
        _seen_ids.add(str(rec["call_id"]))

    records.extend(_synthesize_context_processing_records(events, records))

    return sorted(records, key=lambda r: r["start_ts"])


def _synthesize_context_processing_records(
    events: list[dict], records: list[dict]
) -> list[dict]:
    """Create a ProcessingCall (context-assembly) node before each LLM call.

    The native trace emits a ``context_assembled`` event carrying the fully
    assembled messages (system prompt + injected context) right before each LLM
    call, but no ``processing_call`` event (legacy KG traces had those).  Without
    a node, the system prompt/context has nowhere to live and leaks into the LLM
    or user-input bar.  Synthesize the "first transformation inside the agent":
    a small ProcessingCall that shows the system prompt and injected context,
    sitting between the incoming turn and the LLM call it feeds.
    """
    llm_by_key: dict[tuple, dict] = {}
    for r in records:
        if r.get("call_type") == "LLMCall" and r.get("correlation_id") is not None:
            llm_by_key[(r.get("agent_id"), r["correlation_id"])] = r

    # Per-agent, the end timestamps of real (non-processing) call records — used
    # to anchor each context node right after the call that precedes its LLM (a
    # tool result / prior LLM), so it never overlaps a tool that finished only a
    # fraction of a millisecond before the LLM started.
    _ends_by_agent: dict[str, list[float]] = {}
    for r in records:
        if r.get("level") == "call" and r.get("call_type") != "ProcessingCall":
            _ends_by_agent.setdefault(r.get("agent_id", ""), []).append(r["end_ts"])

    out: list[dict] = []
    seen: set[tuple] = set()
    for ev in sorted(events, key=lambda e: float(e.get("timestamp") or 0)):
        if ev.get("kind") != "context_assembled":
            continue
        msgs = ev.get("messages") or []
        if not msgs:
            continue
        aid = ev.get("agent_id", "")
        corr = ev.get("correlation_id")
        llm = llm_by_key.get((aid, corr))
        if llm is None:  # skip the duplicate corr=0 emission and any unmatched
            continue
        key = (aid, corr)
        if key in seen:
            continue
        seen.add(key)
        # The assembled context (system prompt + injected segments) is the
        # *output* of this step — it must NOT land on the preceding state (which
        # should show the incoming turn: the user question or a tool result).
        # dag.py clears a ProcessingCall's output from the following state, so
        # the system prompt shows only on the ⚙ context bar itself.
        parts: list[str] = []
        for m in msgs:
            if m.get("role") != "system":
                continue
            content = m.get("content") or ""
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            if content:
                parts.append(f"[SYSTEM]\n{content}")
        seg_n = ev.get("segments")
        if isinstance(seg_n, int) and seg_n:
            parts.append(f"({seg_n} context segment{'s' if seg_n != 1 else ''} assembled)")
        cid = f"ctxasm-{aid}-{corr}"
        out.append({
            "call_id": cid,
            "parent_call_id": llm.get("parent_call_id"),
            "_has_ids": True,
            "call_type": "ProcessingCall",
            "level": "call",
            "agent_id": aid,
            # Sit between the preceding call and this LLM: anchor the start at the
            # latest real call that ended before the LLM (a tool result / prior
            # LLM) so the node never overlaps a tool that finished a fraction of a
            # millisecond earlier.  Fall back to a tiny lead when nothing precedes
            # (the agent's first call); Rule 1 then widens it to the agent start.
            "start_ts": max(
                (e for e in _ends_by_agent.get(aid, []) if e <= llm["start_ts"] + 1e-9),
                default=llm["start_ts"] - 0.001,
            ),
            "end_ts": llm["start_ts"],
            # input drives the preceding state — leave empty so the incoming turn
            # (user question / tool result) shown there is not overwritten.
            "input": "",
            "output": "\n\n---\n\n".join(parts).strip(),
            "label": "⚙ context",
            "tool_name": "",
            "model": "",
            "thinking": "",
            "correlation_id": corr,
            "processing_name": "context assembly",
        })
    return out


def _build_call_label(call_type: str, ev: dict) -> str:
    _fn: dict[str, Any] = {
        "MASCall":        lambda e: e.get("mas_name") or e.get("agent_id") or "MAS",
        "AgentCall":      lambda e: e.get("agent_id") or "agent",
        "LLMCall":        lambda e: e.get("model") or "LLM",
        "ToolCall":       lambda e: e.get("tool_name") or e.get("endpoint") or "tool",
        "MemoryCall":     lambda e: e.get("memory_type") or "memory",
        "RAGQuery":       lambda e: "RAG",
        "MITMCall":       lambda e: "⚠ MITM",
        "ProcessingCall": lambda e: (
            _PROC_TYPE_LABEL.get(e.get("processing_type", ""), "")
            or e.get("processing_name")
            or e.get("skill_name")
            or "proc"
        ),
        "ContextState":   lambda e: str(e.get("update_type") or "state")[:22],
    }
    return str(_fn.get(call_type, lambda e: call_type)(ev))[:22]


def _extract_user_input(events: list[dict]) -> str:
    for ev in sorted(events, key=lambda e: float(e.get("timestamp") or 0)):
        if ev.get("kind") == "execution_start":
            ctx = ev.get("context") or {}
            if isinstance(ctx, dict) and ctx.get("is_entry_agent") and ev.get("input"):
                return str(ev["input"])
    for ev in sorted(events, key=lambda e: float(e.get("timestamp") or 0)):
        if ev.get("kind") == "execution_start" and ev.get("input"):
            return str(ev["input"])
    return ""


def _extract_final_output(events: list[dict]) -> str:
    candidates = [
        e for e in events
        if e.get("kind") == "execution_end" and (e.get("output") or e.get("payload"))
    ]
    if not candidates:
        return ""
    last = max(candidates, key=lambda e: float(e.get("timestamp") or 0))
    return str(last.get("output") or last.get("payload") or "")


# ---------------------------------------------------------------------------
# Thinking records — synthesised from LLMCall records with thinking content
# ---------------------------------------------------------------------------

def _synthesize_thinking_records(records: list[dict]) -> list[dict]:
    """Create synthetic ThinkingCall records from LLMCall records that carry thinking text.

    Thinking occupies the first ~85 % of the LLM call wall-clock duration.
    The synthetic end timestamp is:  start + (end - start) * 0.85
    """
    result: list[dict] = []
    for rec in records:
        thinking_text = rec.get("thinking", "")
        if rec.get("call_type") != "LLMCall" or not thinking_text:
            continue
        duration = rec["end_ts"] - rec["start_ts"]
        thinking_end_ts = (
            rec["start_ts"] + duration * 0.85 if duration > 0.0
            else rec["end_ts"] - 0.1
        )
        result.append({
            "call_id":        rec["call_id"] + "-thinking",
            "parent_call_id": rec["call_id"],
            "_has_ids":       True,
            # Internal field — used to retrieve the LLM call end for the thinking lane.
            "_llm_end_ts":    rec["end_ts"],
            "call_type":      "ThinkingCall",
            "level":          "thinking",
            "agent_id":       rec["agent_id"],
            "start_ts":       rec["start_ts"],
            "end_ts":         thinking_end_ts,
            # Input = the LLM prompt that triggered the thinking
            "input":          rec.get("input", ""),
            "output":         thinking_text,
            # Carry the real LLM response for the ThinkingEmit hover_out
            "llm_output":     rec.get("output", ""),
            "label":          "Think",
            "tool_name":      "",
            "model":          rec.get("model", ""),
            "thinking":       "",
        })
    return result
