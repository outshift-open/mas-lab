#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""End-to-end coverage for replay_events_file (previously untested).

Exercises the modified replay path: JSON-parse skipping, per-event
failure isolation, error/success status mapping, and the new
``<app>.graph`` topology span emitted via converter.emit_graph_span.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mas.library.standard.lib.observability.otel.converter import OTEL_AVAILABLE
from mas.library.standard.lib.observability.otel.replay import replay_events_file

pytestmark = pytest.mark.skipif(not OTEL_AVAILABLE, reason="opentelemetry-sdk not installed")


def _write_events(path: Path, events: list) -> None:
    lines = []
    for ev in events:
        lines.append("!!! not json" if ev == "__BAD_JSON__" else json.dumps(ev))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_replay_events_file_end_to_end(tmp_path: Path, monkeypatch) -> None:
    events = [
        {"kind": "system_specification", "agents": [{"id": "planner"}, {"id": "worker"}],
         "app_name": "demo-app"},
        {"kind": "mas_call_start", "call_id": "c1", "run_id": "r1", "session_id": "s1",
         "timestamp": 1.0},
        {"kind": "execution_start", "call_id": "e1", "parent_call_id": "c1",
         "agent_id": "planner", "input": "hi", "timestamp": 1.1},
        {"kind": "execution_end", "call_id": "e1", "agent_id": "planner",
         "status": "error", "output": "boom", "timestamp": 1.2},
        {"kind": "routing", "source_agent_id": "planner", "target_agent_id": "worker",
         "timestamp": 1.3},
        {"kind": "mas_call_end", "call_id": "c1", "status": "success", "result": "done",
         "timestamp": 2.0},
        "__BAD_JSON__",  # skipped during parse, not counted
        # timestamp is a dict -> _ts_ns raises inside the handler -> failed_events branch
        {"kind": "mas_call_start", "call_id": "bad", "timestamp": {}},
    ]
    # Nested run layout so _write_replay_mapping finds run_info.json and a cache dir.
    run_dir = tmp_path / "run"
    spans_dir = run_dir / "spans"
    spans_dir.mkdir(parents=True)
    (run_dir / "run_info.json").write_text(
        json.dumps({"experiment": "exp1", "scenario": "sc1"}), encoding="utf-8"
    )
    (run_dir / "cache").mkdir()
    env_cache = tmp_path / "llm-cache"
    monkeypatch.setenv("MAS_LLM_CACHE_DIR", str(env_cache))

    input_path = run_dir / "events.jsonl"
    output_path = spans_dir / "otel_sdk_spans.jsonl"
    # Leading blank line exercises the empty-line skip in the parse loop.
    input_path.write_text(
        "\n" + "\n".join("!!! bad" if e == "__BAD_JSON__" else json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )

    count = replay_events_file(input_path, output_path, service_name="svc")

    # 7 well-formed JSON records parsed (the bad-JSON line is skipped).
    assert count == 7
    assert output_path.exists()

    spans = [json.loads(line) for line in output_path.read_text().splitlines() if line.strip()]
    assert spans, "expected at least one exported span"
    # App name derived from the event stream, not the service fallback.
    blob = output_path.read_text()
    assert "demo-app.graph" in blob
    # topology JSON carried on the graph span
    assert "gen_ai.ioa.graph" in blob
    # replay mapping was written next to the spans and into the env cache dir.
    mapping = (spans_dir / "session_mappings.jsonl").read_text()
    assert "exp1" in mapping and "sc1" in mapping
    assert (env_cache / "session_mappings.jsonl").exists()


def test_replay_events_file_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        replay_events_file(tmp_path / "nope.jsonl", tmp_path / "out.jsonl")


def test_replay_events_file_explicit_app_name_overrides(tmp_path: Path) -> None:
    events = [
        {"kind": "system_specification", "name": "stream-app", "agents": [{"id": "solo"}]},
        {"kind": "mas_call_start", "call_id": "c1", "timestamp": 1.0},
        {"kind": "mas_call_end", "call_id": "c1", "status": "ok", "timestamp": 2.0},
    ]
    input_path = tmp_path / "events.jsonl"
    output_path = tmp_path / "out.jsonl"
    _write_events(input_path, events)

    count = replay_events_file(input_path, output_path, app_name="explicit-app")
    assert count == 3
    assert "explicit-app.graph" in output_path.read_text()
