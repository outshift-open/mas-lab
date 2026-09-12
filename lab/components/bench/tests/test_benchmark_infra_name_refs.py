#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""CLI --infra must flow into MAS infra_refs for benchmark runs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mas.lab.benchmark.schedule.run_batch.load import LoadedExperiment
from mas.lab.benchmark.schedule.run_batch.prepare import _resolve_run_infra_refs


def test_infra_name_prepends_experiment_local_bundle(tmp_path: Path) -> None:
    infra_dir = tmp_path / "infra"
    infra_dir.mkdir()
    (infra_dir / "gls-vllm.yaml").write_text("apiVersion: infra/v1\n", encoding="utf-8")
    exp_yaml = tmp_path / "experiments.yaml"
    exp_yaml.write_text("experiment:\n  name: t\n", encoding="utf-8")
    mas_dir = tmp_path / "apps" / "demo"
    mas_dir.mkdir(parents=True)
    mas_yaml = mas_dir / "mas.yaml"
    mas_yaml.write_text("apiVersion: mas/v1\n", encoding="utf-8")
    loaded = LoadedExperiment(
        exp=SimpleNamespace(
            execution=SimpleNamespace(infra_refs=["other.yaml"]),
            mas=SimpleNamespace(manifest=mas_yaml),
        ),
        experiment_yaml=exp_yaml,
        configs_dir=None,
        scenario_ids=["s1"],
        dataset_items=[],
        pipeline_specs=[],
        step_overrides_dict={},
        flavour=None,
        flavour_name="local",
        infra_name="gls-vllm",
        n_runs=1,
        trace_cache_dir=None,
    )
    refs = _resolve_run_infra_refs(loaded)
    assert refs[0].endswith("infra/gls-vllm.yaml")
    assert "other.yaml" in refs
