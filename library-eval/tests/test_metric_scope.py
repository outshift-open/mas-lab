#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest
from mas.library.eval.mce.catalog import METRIC_MAP, session_scope
from mas.library.eval.metrics.scope import (
    parse_evidence,
    parse_unit,
    render_judge_input,
)


def test_parse_unit_aliases() -> None:
    assert parse_unit("mas") == "mas"
    assert parse_unit("session") == "mas"
    assert parse_unit("span") == "call"
    with pytest.raises(ValueError, match="mas"):
        parse_unit("workflow")


def test_parse_evidence_aliases() -> None:
    assert parse_evidence("io") == "io"
    assert parse_evidence("trace") == "trajectory"
    with pytest.raises(ValueError, match="trajectory"):
        parse_evidence("kg")


def test_stock_mce_ids_are_mas_io() -> None:
    assert session_scope("groundedness") == ("mas", "io")
    assert session_scope("goal_success_rate") == ("mas", "io")
    assert {"groundedness", "answer_relevancy", "workflow_cohesion_index"} <= set(METRIC_MAP)


def test_render_mas_io_uses_query_and_response(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                '{"kind":"execution_start","parent_call_id":null,"agent_id":"root","input":"plan a trip"}',
                '{"kind":"tool_call_start","agent_id":"root","tool_name":"calc"}',
                '{"kind":"execution_end","agent_id":"root","output":"take the 8:30"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    text, meta = render_judge_input(events, unit="mas", evidence="io")
    assert meta == {"unit": "mas", "evidence": "io", "truncated": False}
    assert "## INPUT" in text
    assert "plan a trip" in text
    assert "## OUTPUT" in text
    assert "take the 8:30" in text
    assert "tool_call_start" not in text
    assert '"kind"' not in text


def test_render_mas_trajectory_includes_events(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"kind":"tool_call_start","tool_name":"calc"}\n',
        encoding="utf-8",
    )
    text, meta = render_judge_input(events, unit="mas", evidence="trajectory")
    assert meta["evidence"] == "trajectory"
    assert "tool_call_start" in text
    assert "## TRACE" in text


def test_render_call_unit_is_rejected(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unit=call"):
        render_judge_input(events, unit="call", evidence="io")
