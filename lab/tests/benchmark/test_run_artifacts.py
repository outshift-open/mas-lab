#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from mas.lab.artifacts import classify_file
from mas.lab.benchmark.pipeline.executor import ExecutionContext
from mas.lab.benchmark.pipeline.resources import ScopeContext
from mas.lab.benchmark.pipeline.run_artifacts import (
    RUN_ARTIFACTS,
    resolve_run_artifact,
    resolve_run_events,
    run_input_stream,
)
from mas.lab.benchmark.schedule.pipeline import materialize_step_dicts
from mas.lab.lab.config import PipelineStepSpec


def _ctx(output_dir: Path) -> ExecutionContext:
    return ExecutionContext(
        pipeline=None,  # type: ignore[arg-type]
        output_dir=output_dir,
        cache_manager=None,  # type: ignore[arg-type]
        scope_context=ScopeContext(
            experiment="exp",
            scenario="full",
            test="item1",
            run="r1",
        ),
    )


def test_resolve_run_artifact_paths(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path / "bench")
    assert resolve_run_artifact(ctx, "kg") == (
        tmp_path / "bench" / "full" / "item1" / "r1" / "kg.json"
    )
    assert resolve_run_artifact(ctx, "trajectory_kg") == (
        tmp_path / "bench" / "full" / "item1" / "r1" / "trajectory-kg.html"
    )
    assert resolve_run_artifact(ctx, "kg_otel") == (
        tmp_path / "bench" / "full" / "item1" / "r1" / "kg_otel.json"
    )


def test_resolve_run_events_via_run_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache" / "traces" / "abc123"
    events = cache_root / "traces" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text('{"kind":"test"}\n', encoding="utf-8")

    run_dir = tmp_path / "bench" / "full" / "item1" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / ".run_ref").write_text("abc123", encoding="utf-8")

    monkeypatch.setattr(
        "mas.lab.benchmark.cache.trace_store.trace_cache_roots",
        lambda explicit=None: [tmp_path / "cache" / "traces"],
    )

    ctx = _ctx(tmp_path / "bench")
    resolved = resolve_run_events(ctx, {"run_dir": str(run_dir)})
    assert resolved == events


def test_run_input_stream_includes_run_and_trace(tmp_path: Path) -> None:
    run_dir = tmp_path / "bench" / "full" / "item1" / "r1"
    trace = run_dir / "traces" / "events.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text('{"kind":"test"}\n', encoding="utf-8")

    ctx = _ctx(tmp_path / "bench")
    payload = run_input_stream(ctx, {"run_dir": str(run_dir)})
    assert payload["run_dir"] == str(run_dir.resolve())
    assert payload["scenario"] == "full"
    assert payload["events_path"] == str(trace.resolve())


def test_materialize_per_run_steps(tmp_path: Path) -> None:
    run_dir = tmp_path / "full" / "item1" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / ".run_ref").write_text("deadbeef", encoding="utf-8")

    specs = [
        PipelineStepSpec(
            type="plot_multilevel_trajectory",
            name="plot-native",
            phase="post",
            per_run=True,
        ),
        PipelineStepSpec(
            type="plot_multilevel_trajectory_kg",
            name="plot-kg",
            phase="post",
            per_run=True,
            depends_on=["normalize-native"],
        ),
    ]
    steps = materialize_step_dicts(
        specs,
        phase="post",
        scenario_ids=["full", "baseline"],
        infra_name=None,
        step_overrides={},
        template_vars={"output_dir": str(tmp_path)},
    )
    assert len(steps) == 2
    assert steps[0]["name"] == "plot-native-full-item1-r1"
    assert steps[0]["config"]["run"] == "r1"
    assert steps[0]["config"]["run_dir"] == str(run_dir.resolve())


def test_classify_run_artifacts() -> None:
    assert classify_file(Path("kg.json")).abbrev == "KG"
    assert classify_file(Path("trajectory-native.html")).abbrev == "TrajNative"
    assert classify_file(Path("trajectory-kg.html")).abbrev == "TrajKG"
    assert classify_file(Path("validation_report.json")).abbrev == "Validation"
    assert classify_file(Path("parity_report.json")).abbrev == "Parity"
    assert classify_file(Path("otel_sdk_spans_replay.jsonl")).abbrev == "OtelReplay"


def test_registry_has_both_trajectory_plotters() -> None:
    native = RUN_ARTIFACTS["trajectory_native"]
    kg = RUN_ARTIFACTS["trajectory_kg"]
    assert "plot_multilevel_trajectory" in native.produced_by
    assert "plot_multilevel_trajectory_kg" in kg.produced_by


def test_kg_plotter_processor_registered() -> None:
    import mas.lab.graph  # noqa: F401 — registers internal processor

    from mas.lab.processor import get_processor

    cls = get_processor("multilevel_trajectory_kg_plotter")
    assert cls.name == "multilevel_trajectory_kg_plotter"
