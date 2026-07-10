#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Multilevel trajectory plot from native events.jsonl (OSS path)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EVENTS_FIXTURE = (
    REPO_ROOT / "docs/tutorials/03-experiments-and-analysis/fixtures/events.jsonl"
)


@pytest.mark.parametrize("fmt", ["html", "svg"])
def test_multilevel_plot_renders_from_events_jsonl(fmt: str, tmp_path: Path) -> None:
    pytest.importorskip("mas.lab.plots.multilevel_trajectory")
    from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory
    from mas.lab.plots.trajectory import load_trace

    assert EVENTS_FIXTURE.is_file(), f"missing fixture: {EVENTS_FIXTURE}"
    events = load_trace(EVENTS_FIXTURE)
    assert events, "fixture events.jsonl should not be empty"

    rendered = plot_multilevel_trajectory(events, fmt=fmt, title="Tutorial 03 fixture")
    assert len(rendered) > 200
    if fmt == "html":
        assert "<" in rendered
    else:
        assert "<svg" in rendered

    out = tmp_path / f"multilevel.{fmt if fmt != 'html' else 'html'}"
    out.write_text(rendered, encoding="utf-8")
    assert out.stat().st_size > 200


def _tool_loop_events() -> list[dict]:
    """A single-agent tool-use loop (LLM → tool → LLM), each engine op emitted
    twice (~1 ms apart) as the native observability layer does, and with the
    follow-up LLM mis-parented under the tool (the runtime call-stack does not
    pop the completed tool frame). Mirrors the real tutorial-02 trace."""
    moder, tool_cid, llm1, llm2 = "moderator", "tool-1", "llm-1", "llm-2"
    return [
        {"kind": "mas_call_start", "call_id": "mas-1", "agent_id": "mas", "timestamp": 0.0},
        {"kind": "execution_start", "call_id": moder, "parent_call_id": "mas-1",
         "agent_id": moder, "timestamp": 0.0, "input": "hi"},
        # LLM 1 (double-emitted) — child of the agent
        {"kind": "llm_call_start", "call_id": llm1, "parent_call_id": moder,
         "agent_id": moder, "correlation_id": 1, "timestamp": 0.0},
        {"kind": "llm_call_start", "call_id": llm1, "parent_call_id": moder,
         "agent_id": moder, "correlation_id": 1, "timestamp": 0.001},
        {"kind": "llm_call_end", "call_id": llm1, "agent_id": moder,
         "correlation_id": 1, "timestamp": 1.6},
        {"kind": "llm_call_end", "call_id": llm1, "agent_id": moder,
         "correlation_id": 1, "timestamp": 1.601},
        # Tool (double-emitted) — child of the agent
        {"kind": "tool_call_start", "call_id": tool_cid, "parent_call_id": moder,
         "agent_id": moder, "correlation_id": 2, "timestamp": 1.61, "tool_name": "contract_call"},
        {"kind": "tool_call_start", "call_id": tool_cid, "parent_call_id": moder,
         "agent_id": moder, "correlation_id": 2, "timestamp": 1.611, "tool_name": "contract_call"},
        {"kind": "tool_call_end", "call_id": tool_cid, "agent_id": moder,
         "correlation_id": 2, "timestamp": 8.0, "tool_name": "contract_call"},
        # LLM 2 (double-emitted) — MIS-PARENTED under the tool; starts after the
        # tool already ended, so it is really a sibling of the tool.
        {"kind": "llm_call_start", "call_id": llm2, "parent_call_id": tool_cid,
         "agent_id": moder, "correlation_id": 3, "timestamp": 8.01},
        {"kind": "llm_call_start", "call_id": llm2, "parent_call_id": tool_cid,
         "agent_id": moder, "correlation_id": 3, "timestamp": 8.011},
        {"kind": "llm_call_end", "call_id": llm2, "agent_id": moder,
         "correlation_id": 3, "timestamp": 9.3, "output": "done"},
        {"kind": "llm_call_end", "call_id": llm2, "agent_id": moder,
         "correlation_id": 3, "timestamp": 9.301, "output": "done"},
        {"kind": "execution_end", "call_id": moder, "agent_id": moder,
         "timestamp": 9.3, "output": "done"},
        {"kind": "mas_call_end", "call_id": "mas-1", "agent_id": "mas", "timestamp": 9.3},
    ]


def test_duplicate_engine_ops_are_deduped() -> None:
    """Each engine op is emitted twice by the native layer; records.py must keep
    exactly one record per op so bars are not doubled/overlapped."""
    from mas.lab.plots.multilevel_trajectory.records import _build_call_records

    recs = _build_call_records(_tool_loop_events())
    calls = [r for r in recs if r["level"] == "call"]
    assert [(r["call_type"], r["label"]) for r in calls] == [
        ("LLMCall", "LLM"),
        ("ToolCall", "contract_call"),
        ("LLMCall", "LLM"),
    ]


def test_followup_llm_reparented_off_completed_tool() -> None:
    """A follow-up LLM mis-parented under a tool that already ended must be
    re-parented to the grandparent (the agent), so boundary alignment does not
    stretch the tool to contain it (which would drop the tool bar)."""
    from mas.lab.plots.multilevel_trajectory.records import _build_call_records

    recs = _build_call_records(_tool_loop_events())
    by_type = {r["call_type"]: r for r in recs if r["level"] == "call"}
    # Both LLM records now hang off the agent, not the tool.
    llms = [r for r in recs if r["call_type"] == "LLMCall"]
    assert all(r["parent_call_id"] == "moderator" for r in llms)
    assert by_type["ToolCall"]["parent_call_id"] == "moderator"


def test_tool_loop_dag_has_no_overlap() -> None:
    """End-to-end: the DAG for a tool-use loop keeps three distinct call bars
    (LLM → tool → LLM) with no overlapping transitions in the Calls lane."""
    from mas.lab.plots.multilevel_trajectory.dag import _build_dag
    from mas.lab.plots.multilevel_trajectory.records import _build_call_records

    events = _tool_loop_events()
    _state_reg, lanes = _build_dag(_build_call_records(events), events)
    calls_lane = next(l for l in lanes if l.lane_id == "calls")
    bars = [el for el in calls_lane.sequence if getattr(el, "call_type", None)]
    assert [b.label for b in bars] == ["LLM", "contract_call", "LLM"]
    # No two consecutive call bars overlap in time.
    for a, b in zip(bars, bars[1:]):
        assert a.end_ts <= b.start_ts + 1e-6, f"{a.label} overlaps {b.label}"


def _delegation_events() -> list[dict]:
    """A moderator that delegates one turn to a peer (schedule_agent).

    Mirrors the native multi-agent trace: the peer runs inside the moderator's
    delegation tool call and — arriving via the peer bus — parents to the MAS
    call rather than the moderator.  Both agents' engine ops restart their
    correlation ids at 1 (per-agent operators)."""
    mod, sched = "moderator", "schedule_agent"
    return [
        {"kind": "mas_call_start", "call_id": "mas-1", "agent_id": "mas", "timestamp": 0.0},
        {"kind": "execution_start", "call_id": mod, "parent_call_id": "mas-1",
         "agent_id": mod, "timestamp": 0.0, "input": "plan a trip"},
        {"kind": "llm_call_start", "call_id": "m-llm-1", "parent_call_id": mod,
         "agent_id": mod, "correlation_id": 1, "timestamp": 0.0},
        {"kind": "llm_call_end", "call_id": "m-llm-1", "agent_id": mod,
         "correlation_id": 1, "timestamp": 1.0},
        # Delegation tool on the moderator; the peer runs inside its window.
        {"kind": "tool_call_start", "call_id": "deleg-1", "parent_call_id": mod,
         "agent_id": mod, "correlation_id": 2, "timestamp": 1.1, "tool_name": "contract_call"},
        {"kind": "execution_start", "call_id": "sched-exec", "parent_call_id": "mas-1",
         "agent_id": sched, "timestamp": 1.2, "input": "check schedule"},
        {"kind": "llm_call_start", "call_id": "s-llm-1", "parent_call_id": "sched-exec",
         "agent_id": sched, "correlation_id": 1, "timestamp": 1.3},
        {"kind": "llm_call_end", "call_id": "s-llm-1", "agent_id": sched,
         "correlation_id": 1, "timestamp": 3.0, "output": "no routes"},
        {"kind": "execution_end", "call_id": "sched-exec", "agent_id": sched, "timestamp": 3.1},
        {"kind": "tool_call_end", "call_id": "deleg-1", "agent_id": mod,
         "correlation_id": 2, "timestamp": 3.2, "tool_name": "contract_call"},
        # Moderator resumes and synthesises the final answer.
        {"kind": "llm_call_start", "call_id": "m-llm-2", "parent_call_id": mod,
         "agent_id": mod, "correlation_id": 3, "timestamp": 3.3},
        {"kind": "llm_call_end", "call_id": "m-llm-2", "agent_id": mod,
         "correlation_id": 3, "timestamp": 4.5, "output": "here is your plan"},
        {"kind": "execution_end", "call_id": mod, "agent_id": mod, "timestamp": 4.5},
        {"kind": "mas_call_end", "call_id": "mas-1", "agent_id": "mas", "timestamp": 4.5},
    ]


def test_delegation_agent_lane_interleaves_moderator_and_peer() -> None:
    """A delegated peer must appear on the Agent lane with the delegating agent
    resuming after it: moderator → schedule_agent → moderator."""
    from mas.lab.plots.multilevel_trajectory.dag import _build_dag
    from mas.lab.plots.multilevel_trajectory.records import _build_call_records

    events = _delegation_events()
    _state_reg, lanes = _build_dag(_build_call_records(events), events)
    agents = next(l for l in lanes if l.lane_id == "agents")
    labels = [el.label for el in agents.sequence if getattr(el, "call_type", None)]
    assert labels == ["moderator", "schedule_agent", "moderator"], labels


def test_delegation_peer_llm_not_deduped_against_entry() -> None:
    """Per-agent correlation ids collide (both restart at 1); the peer's LLM
    must survive dedup and reach the Calls lane."""
    from mas.lab.plots.multilevel_trajectory.records import _build_call_records

    recs = _build_call_records(_delegation_events())
    llm_agents = sorted(
        r["agent_id"] for r in recs if r["call_type"] == "LLMCall"
    )
    # moderator (×2) + schedule_agent (×1) — the peer LLM was not swallowed.
    assert llm_agents == ["moderator", "moderator", "schedule_agent"], llm_agents


def test_delegation_tool_hidden_from_calls_lane() -> None:
    """The delegation tool is represented by the peer on the Agent lane, so it
    must not also appear as a bar on the Calls lane."""
    from mas.lab.plots.multilevel_trajectory.dag import _build_dag
    from mas.lab.plots.multilevel_trajectory.records import _build_call_records

    events = _delegation_events()
    _state_reg, lanes = _build_dag(_build_call_records(events), events)
    calls = next(l for l in lanes if l.lane_id == "calls")
    labels = [el.label for el in calls.sequence if getattr(el, "call_type", None)]
    assert "contract_call" not in labels, labels
    assert labels.count("LLM") == 3, labels


def test_multilevel_cli_from_events_jsonl(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from mas.lab.cli import app as cli

    runner = CliRunner()
    out = tmp_path / "swimlane.html"
    result = runner.invoke(
        cli,
        [
            "plot",
            "multilevel-trajectory",
            str(EVENTS_FIXTURE),
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert out.stat().st_size > 200
