#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from pathlib import Path

from mas.lab.benchmark.metadata import BenchmarkMetadata, BenchmarkStatus
from mas.lab.benchmark.run_manager import BenchmarkRunManager


def _write_metadata(path: Path, *, experiment: str, benchmark_id: str) -> None:
    meta = BenchmarkMetadata(
        benchmark_id=benchmark_id,
        timestamp=datetime.now().isoformat(),
        experiment_name=experiment,
        experiment_description="",
        experiment_yaml_path="/tmp/exp.yaml",
        status=BenchmarkStatus.COMPLETED,
        total_scenarios=1,
        started_at=datetime.now().isoformat(),
        run_dir=str(path),
        results_file=str(path / "results.csv"),
        plots_dir=str(path / "plots"),
    )
    meta.to_yaml(path / "metadata.yaml")


def test_list_finds_flat_metadata_at_output_root(tmp_path):
    out = tmp_path / "smoke-out"
    out.mkdir()
    _write_metadata(out, experiment="smoke-trip-planner", benchmark_id="11111111-1111-1111-1111-111111111111")

    mgr = BenchmarkRunManager(benchmarks_root=out)
    runs = mgr.list_runs()
    assert len(runs) == 1
    assert runs[0].experiment_name == "smoke-trip-planner"


def test_list_finds_nested_timestamp_directories(tmp_path):
    root = tmp_path / "labs"
    nested = root / "2026-07-01_12-00-00_deadbeef"
    nested.mkdir(parents=True)
    _write_metadata(nested, experiment="nested-run", benchmark_id="22222222-2222-2222-2222-222222222222")

    mgr = BenchmarkRunManager(benchmarks_root=root)
    runs = mgr.list_runs()
    assert len(runs) == 1
    assert runs[0].experiment_name == "nested-run"


def test_list_scans_runs_root_when_different_from_labs(tmp_path, monkeypatch):
    labs = tmp_path / "labs"
    runs = tmp_path / "runs"
    labs.mkdir()
    runs.mkdir()
    _write_metadata(runs, experiment="in-runs-dir", benchmark_id="33333333-3333-3333-3333-333333333333")

    monkeypatch.setattr(
        "mas.lab.benchmark.run_manager.manager.default_search_roots",
        lambda extra=None: [labs.resolve(), runs.resolve()],
    )
    mgr = BenchmarkRunManager(benchmarks_root=labs)
    listed = mgr.list_runs()
    assert any(r.experiment_name == "in-runs-dir" for r in listed)
