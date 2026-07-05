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

    for ev in sorted(events, key=lambda e: float(e.get("timestamp") or 0)):
        kind      = ev.get("kind", "")
        kind_base = kind.replace("_start", "").replace("_end", "")
        agent_id  = ev.get("agent_id", "")
        tool_name = ev.get("tool_name", "")
        call_type = _KIND_BASE_TO_TYPE.get(kind_base)
        if call_type is None:
            continue
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
                "processing_name": ev.get("processing_name", "") if call_type == "ProcessingCall" else "",
            }
            # Preserve per-actor context segments from ProcessingCall events
            # so the trajectory card can build CPR data directly.
            if call_type == "ProcessingCall" and ev.get("segments"):
                record["segments"] = ev["segments"]
            if call_type == "LLMCall" and ev.get("messages"):
                msgs = ev["messages"]
                if isinstance(msgs, list) and msgs:
                    lines: list[str] = []
                    for m in msgs:
                        role = m.get("role", "?")
                        if role == "tool":
                            continue
                        content = m.get("content") or ""
                        if isinstance(content, list):
                            content = " ".join(
                                p.get("text", "") for p in content if isinstance(p, dict)
                            )
                        if not content:
                            continue
                        lines.append(f"[{role.upper()}]\n{str(content)}")
                    record["input"] = "\n\n---\n\n".join(lines)
            if call_type == "ToolCall" and not record["input"]:
                # tool_call_start stores params in 'arguments', not 'input'
                raw_args = ev.get("arguments")
                if raw_args is not None and str(raw_args).strip() not in ("", "None", "null", "{}"):
                    record["input"] = str(raw_args)
                else:
                    # At minimum show which tool is being called
                    record["input"] = f"→ {ev.get('tool_name') or 'tool'}()"
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

    return sorted(records, key=lambda r: r["start_ts"])


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
