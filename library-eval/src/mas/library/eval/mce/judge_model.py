#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve the LLM-as-judge model for MCE evals.

Default is the **same model the agent used** (experiment metadata, then
workspace infra). Override on the lab spec (``experiment.evaluation.model``)
or per ``eval_mce`` step (``config.model``). See
``docs/manifests/summarization.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from mas.runtime.spec.model_ref import first_nonempty


@dataclass(frozen=True)
class ResolvedJudgeModel:
    """Effective MCE judge model plus the spec field it came from."""

    model: Optional[str]
    source: str

    def __bool__(self) -> bool:
        return bool(self.model)


def _nonempty(value: Any) -> Optional[str]:
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def resolve_judge_model(
    *,
    step_model: Any = None,
    step_judge_model: Any = None,
    evaluation_model: Any = None,
    evaluation_config: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    template_vars: Mapping[str, Any] | None = None,
) -> ResolvedJudgeModel:
    """Precedence (first non-empty wins).

    1. ``eval_mce`` step ``config.model``
    2. ``eval_mce`` step ``config.judge_model``
    3. ``experiment.evaluation.model``
    4. ``experiment.evaluation.config.model``
    5. pipeline ``template_vars.eval_model`` / ``judge_model``
    6. ``experiment.metadata.model_name`` / ``model`` / ``judge_model``
    7. infra default (caller; source ``infra``)
    """
    cfg = evaluation_config or {}
    tmpl = template_vars or {}
    meta = metadata or {}
    model, source = first_nonempty(
        (step_model, "eval_mce.config.model"),
        (step_judge_model, "eval_mce.config.judge_model"),
        (evaluation_model, "experiment.evaluation.model"),
        (cfg.get("model"), "experiment.evaluation.config.model"),
        (cfg.get("judge_model"), "experiment.evaluation.config.judge_model"),
        (tmpl.get("eval_model"), "template_vars.eval_model"),
        (tmpl.get("judge_model"), "template_vars.judge_model"),
        (meta.get("model_name"), "experiment.metadata.model_name"),
        (meta.get("model"), "experiment.metadata.model"),
        (meta.get("judge_model"), "experiment.metadata.judge_model"),
    )
    return ResolvedJudgeModel(model, source or "infra")


def apply_eval_mce_model_defaults(
    steps: list[Any],
    resolved: ResolvedJudgeModel,
) -> None:
    """Set ``config.model`` on ``eval_mce`` steps that omitted it."""
    if not resolved.model:
        return
    for step in steps:
        if getattr(step, "type", None) != "eval_mce":
            continue
        config = getattr(step, "config", None)
        if not isinstance(config, dict):
            continue
        if _nonempty(config.get("model") or config.get("judge_model")):
            continue
        config["model"] = resolved.model
        config.setdefault("model_source", resolved.source)
