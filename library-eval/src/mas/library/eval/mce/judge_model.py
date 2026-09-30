#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve the LLM-as-judge model for MCE evals.

There is no workspace-global model in the committed spec. Default is:

1. ``eval_mce.config.model`` / ``experiment.evaluation.model`` (role overrides)
2. ``experiment.models.judge``
3. ``experiment.model`` / ``experiment.models.main`` (``any`` means inherit)
4. MAS ``spec.models[]`` (MAS default; ``any`` means inherit)
5. unique concrete Agent ``spec.models[]``
6. local ``config.yaml`` ``defaults.model`` (only when the spec said ``any``)

See ``docs/manifests/summarization.md``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from mas.runtime.spec.model_ref import first_concrete, primary_model_string
from mas.runtime.spec.source import load_yaml_mapping, resolve_yaml_path

_log = logging.getLogger(__name__)


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


def _agent_entries(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    spec = doc.get("spec")
    spec = spec if isinstance(spec, dict) else {}
    agency = spec.get("agency")
    agency = agency if isinstance(agency, dict) else {}
    agents = agency.get("agents")
    if not isinstance(agents, list):
        agents = spec.get("agents")
    if not isinstance(agents, list):
        return []
    return [a for a in agents if isinstance(a, dict)]


def collect_application_primary_models(
    manifest_path: Path | None,
) -> list[tuple[str, str]]:
    """Primary ``spec.models[]`` strings from an Agent or MAS application.

    MAS agent ``ref`` paths resolve relative to the MAS manifest. Agents that
    omit ``spec.models`` are skipped — they are not filled from defaults.yaml.
    """
    if manifest_path is None:
        return []
    path = Path(manifest_path)
    if not path.is_file():
        return []
    try:
        doc = load_yaml_mapping(path)
    except (OSError, ValueError):
        return []
    kind = str(doc.get("kind") or "").strip().lower()
    mas_default = primary_model_string(doc)
    if mas_default:
        return [(mas_default, "application.spec.models")]
    if kind == "agent":
        return []
    found: list[tuple[str, str]] = []
    for agent in _agent_entries(doc):
        if "spec" in agent or str(agent.get("kind") or "").strip().lower() == "agent":
            model = primary_model_string(agent)
            if model:
                found.append((model, "application.spec.models"))
            continue
        ref = agent.get("ref")
        if not ref:
            continue
        try:
            nested_path = resolve_yaml_path(str(ref), path.parent)
            nested = load_yaml_mapping(nested_path)
        except (OSError, ValueError, FileNotFoundError):
            continue
        model = primary_model_string(nested)
        if model:
            found.append((model, "application.spec.models"))
    return found


def unique_application_model(manifest_path: Path | None) -> tuple[str | None, str]:
    """MAS ``spec.models[]`` if concrete, else unique concrete agent primary.

    ``any`` is skipped. Mixed concrete agent models without a MAS default
    is not a pin — set ``experiment.models`` or ``experiment.evaluation.model``.
    """
    found = collect_application_primary_models(manifest_path)
    models = {model for model, _ in found}
    if len(models) == 1:
        return next(iter(models)), found[0][1]
    if len(models) > 1:
        _log.warning(
            "application agents declare more than one primary model %s; "
            "set experiment.models or experiment.evaluation.model",
            sorted(models),
        )
    return None, ""


def resolve_judge_model(
    *,
    step_model: Any = None,
    step_judge_model: Any = None,
    evaluation_model: Any = None,
    evaluation_config: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    template_vars: Mapping[str, Any] | None = None,
    application_model: Any = None,
    application_source: str = "application.spec.models",
    experiment_model: Any = None,
    experiment_judge_model: Any = None,
) -> ResolvedJudgeModel:
    """Precedence (first concrete wins; ``any`` is skipped).

    1. ``eval_mce`` step ``config.model``
    2. ``eval_mce`` step ``config.judge_model``
    3. ``experiment.evaluation.model`` (judge override)
    4. ``experiment.evaluation.config.model``
    5. pipeline ``template_vars.eval_model`` / ``judge_model``
    6. ``experiment.models.judge``
    7. ``experiment.model`` / ``experiment.models.main``
    8. application MAS/Agent ``spec.models[]``
    9. ``experiment.metadata.model_name`` (legacy annotation)
    10. local ``config.yaml`` / package ``defaults.model`` (caller; ``any``)
    """
    cfg = evaluation_config or {}
    tmpl = template_vars or {}
    meta = metadata or {}
    app_source = str(application_source or "").strip() or "application.spec.models"
    model, source = first_concrete(
        (step_model, "eval_mce.config.model"),
        (step_judge_model, "eval_mce.config.judge_model"),
        (evaluation_model, "experiment.evaluation.model"),
        (cfg.get("model"), "experiment.evaluation.config.model"),
        (cfg.get("judge_model"), "experiment.evaluation.config.judge_model"),
        (tmpl.get("eval_model"), "template_vars.eval_model"),
        (tmpl.get("judge_model"), "template_vars.judge_model"),
        (experiment_judge_model, "experiment.models.judge"),
        (experiment_model, "experiment.model"),
        (application_model, app_source),
        (meta.get("model_name"), "experiment.metadata.model_name"),
        (meta.get("model"), "experiment.metadata.model"),
        (meta.get("judge_model"), "experiment.metadata.judge_model"),
    )
    return ResolvedJudgeModel(model, source or "defaults.model")


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
