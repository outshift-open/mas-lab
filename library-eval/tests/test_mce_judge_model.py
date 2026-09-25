#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.library.eval.mce.judge_model import (
    apply_eval_mce_model_defaults,
    resolve_judge_model,
)


def test_default_is_infra_when_nothing_set() -> None:
    resolved = resolve_judge_model()
    assert resolved.model is None
    assert resolved.source == "infra"
    assert not resolved


def test_step_model_wins() -> None:
    resolved = resolve_judge_model(
        step_model="gpt-4o",
        evaluation_model="gpt-4o-mini",
        metadata={"model_name": "haiku"},
    )
    assert resolved.model == "gpt-4o"
    assert resolved.source == "eval_mce.config.model"


def test_evaluation_model_before_metadata() -> None:
    resolved = resolve_judge_model(
        evaluation_model="gpt-4o-mini",
        metadata={"model_name": "gpt-4o"},
    )
    assert (resolved.model, resolved.source) == (
        "gpt-4o-mini",
        "experiment.evaluation.model",
    )


def test_evaluation_config_model_alias() -> None:
    resolved = resolve_judge_model(evaluation_config={"model": "judge-x"})
    assert (resolved.model, resolved.source) == (
        "judge-x",
        "experiment.evaluation.config.model",
    )


def test_metadata_model_name_is_agent_default() -> None:
    resolved = resolve_judge_model(metadata={"model_name": "gpt-4o"})
    assert (resolved.model, resolved.source) == (
        "gpt-4o",
        "experiment.metadata.model_name",
    )


def test_template_vars_eval_model() -> None:
    resolved = resolve_judge_model(template_vars={"eval_model": "tmpl-judge"})
    assert resolved.model == "tmpl-judge"
    assert resolved.source == "template_vars.eval_model"


def test_empty_strings_are_skipped() -> None:
    resolved = resolve_judge_model(
        step_model="  ",
        evaluation_model="",
        metadata={"model_name": "gpt-4o"},
    )
    assert resolved.model == "gpt-4o"


class _Step:
    def __init__(self, type: str, config: dict | None = None) -> None:
        self.type = type
        self.config = config if config is not None else {}


def test_apply_defaults_fills_omitted_eval_mce_only() -> None:
    from mas.library.eval.mce.judge_model import ResolvedJudgeModel

    steps = [
        _Step("eval_mce", {}),
        _Step("eval_mce", {"model": "already"}),
        _Step("extract_trajectories", {}),
    ]
    apply_eval_mce_model_defaults(
        steps, ResolvedJudgeModel("gpt-4o-mini", "experiment.evaluation.model")
    )
    assert steps[0].config["model"] == "gpt-4o-mini"
    assert steps[0].config["model_source"] == "experiment.evaluation.model"
    assert steps[1].config["model"] == "already"
    assert "model" not in steps[2].config


def test_step_judge_model_alias() -> None:
    resolved = resolve_judge_model(
        step_judge_model="haiku",
        evaluation_model="gpt-4o-mini",
    )
    assert (resolved.model, resolved.source) == (
        "haiku",
        "eval_mce.config.judge_model",
    )


def test_apply_defaults_skips_judge_model_only_step() -> None:
    from mas.library.eval.mce.judge_model import ResolvedJudgeModel

    steps = [_Step("eval_mce", {"judge_model": "already"})]
    apply_eval_mce_model_defaults(
        steps, ResolvedJudgeModel("gpt-4o-mini", "experiment.evaluation.model")
    )
    assert steps[0].config == {"judge_model": "already"}


def test_template_vars_after_evaluation_model() -> None:
    resolved = resolve_judge_model(
        evaluation_model="gpt-4o-mini",
        template_vars={"eval_model": "tmpl-judge"},
    )
    assert resolved.model == "gpt-4o-mini"
