#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.lab.benchmark.experiment import EvaluationSpec
from mas.lab.lab.config.experiment_base import MASRunBase


def test_evaluation_spec_positional_config_still_works() -> None:
    spec = EvaluationSpec("llm_judge", {"foo": 1})
    assert spec.method == "llm_judge"
    assert spec.config == {"foo": 1}
    assert spec.model is None


def test_evaluation_spec_reads_top_level_model() -> None:
    spec = EvaluationSpec.from_dict({"method": "llm_judge", "model": "gpt-4o-mini"})
    assert spec.method == "llm_judge"
    assert spec.model == "gpt-4o-mini"


def test_evaluation_spec_config_model_alias() -> None:
    spec = EvaluationSpec.from_dict(
        {"method": "llm_judge", "config": {"model": "haiku"}}
    )
    assert spec.model == "haiku"


def test_evaluation_spec_top_level_wins_over_config() -> None:
    spec = EvaluationSpec.from_dict(
        {"method": "llm_judge", "model": "gpt-4o-mini", "config": {"model": "ignored"}}
    )
    assert spec.model == "gpt-4o-mini"


def test_experiment_injects_eval_mce_model(tmp_path) -> None:
    data = {
        "name": "judge-override",
        "evaluation": {"method": "llm_judge", "model": "gpt-4o-mini"},
        "application": {
            "post": [
                {"type": "extract_trajectories"},
                {"type": "eval_mce", "depends_on": ["extract_trajectories"]},
                {"type": "eval_mce", "name": "strict", "config": {"model": "gpt-4o"}},
            ]
        },
    }
    loaded = MASRunBase._load_base_fields(
        data, tmp_path, yaml_path=tmp_path / "experiment.yaml"
    )
    steps = loaded["levels"]["application"].pipeline
    mce = [s for s in steps if s.type == "eval_mce"]
    assert len(mce) == 2
    inherited = next(s for s in mce if s.name != "strict")
    strict = next(s for s in mce if s.name == "strict")
    assert inherited.config["model"] == "gpt-4o-mini"
    assert inherited.config["model_source"] == "experiment.evaluation.model"
    assert strict.config["model"] == "gpt-4o"


def test_experiment_metadata_model_name_defaults_judge(tmp_path) -> None:
    data = {
        "name": "same-model",
        "metadata": {"model_name": "gpt-4o"},
        "application": {"post": [{"type": "eval_mce"}]},
    }
    loaded = MASRunBase._load_base_fields(
        data, tmp_path, yaml_path=tmp_path / "experiment.yaml"
    )
    step = loaded["levels"]["application"].pipeline[0]
    assert step.config["model"] == "gpt-4o"
    assert step.config["model_source"] == "experiment.metadata.model_name"
