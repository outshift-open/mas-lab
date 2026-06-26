#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for unified pipeline resolution and phase execution."""
from __future__ import annotations

from pathlib import Path

import yaml

from mas.lab.benchmark.schedule.pipeline import materialize_step_dicts
from mas.lab.benchmark.schedule.pipeline_resolve import resolve_pipeline_specs
from mas.lab.lab.config import PipelineStepSpec


def test_resolve_inline_specs_from_experiment_dict():
    class _Exp:
        name = "demo"
        pipeline = [
            PipelineStepSpec(type="extract_trace_stats", name="trace-stats", phase="post"),
            PipelineStepSpec(type="service_start", name="start", phase="pre"),
        ]

        def all_pipeline_steps(self):
            return list(self.pipeline)

    specs = resolve_pipeline_specs(_Exp(), Path("/tmp/experiment.yaml"))
    assert len(specs) == 2
    assert {s.phase for s in specs} == {"pre", "post"}


def test_resolve_sibling_pipeline_yaml(tmp_path: Path):
    sibling = tmp_path / "pipeline.yaml"
    sibling.write_text(
        yaml.dump(
            {
                "pipeline": {
                    "name": "post",
                    "steps": [
                        {"name": "stats", "type": "extract_trace_stats", "phase": "post"},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    class _Exp:
        name = "demo"
        pipeline = []

        def all_pipeline_steps(self):
            return []

    specs = resolve_pipeline_specs(_Exp(), tmp_path / "experiment.yaml")
    assert len(specs) == 1
    assert specs[0].type == "extract_trace_stats"


def test_materialize_filters_by_phase():
    specs = [
        PipelineStepSpec(type="service_start", name="start", phase="pre"),
        PipelineStepSpec(type="extract_trace_stats", name="stats", phase="post"),
    ]
    pre = materialize_step_dicts(specs, phase="pre", scenario_ids=["s1"], infra_name=None, step_overrides={})
    post = materialize_step_dicts(specs, phase="post", scenario_ids=["s1"], infra_name=None, step_overrides={})
    assert [s["name"] for s in pre] == ["start"]
    assert [s["name"] for s in post] == ["stats"]
