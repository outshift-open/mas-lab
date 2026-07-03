#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Compose runner — MAS + deployment → EffectiveBind + PlacementPlan."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mas.ctl.compose.models import EffectiveBindManifest, ResolvedInfra
from mas.ctl.compose.pipeline import (
    PlacementPlan,
    compose_application,
    compose_effective_bind,
    compose_placement_from_deployment,
)
from mas.ctl.compose.placement_validate import validate_placement_strategy
from mas.ctl.deployment.load import load_deployment, resolve_runtime_id
from mas.ctl.infra.resolve import resolve_infra_refs
from mas.runtime.spec.source import load_yaml_mapping
from mas.ctl.overlay import merge_overlay
from mas.ctl.validate import validate_file, validation_enabled
from mas.ctl.workspace.config import (
    UserConfig,
    WorkspaceConfig,
    collect_infra_interceptors,
    collect_mas_infra_refs,
    merge_infra_interceptors,
    merge_infra_refs,
)


@dataclass
class ComposeRequest:
    manifest: Path
    deployment_path: Path | None = None
    overlay_ids: list[str] = field(default_factory=list)
    overlay_paths: list[Path] = field(default_factory=list)
    infra_refs: list[str] = field(default_factory=list)
    kernel_backend: str | None = None  # CLI override of deployment.spec.runtime_id
    validate: bool = True


@dataclass
class ComposeResult:
    mas_id: str
    mas_config: dict[str, Any]
    effective_bind: dict[str, Any]
    placement_plan: dict[str, Any]
    deployment: dict[str, Any]
    infra_refs: list[str]
    bind: EffectiveBindManifest
    plan: PlacementPlan
    resolved_infra: ResolvedInfra | None = None


def _effective_bind_to_dict(bind: EffectiveBindManifest) -> dict[str, Any]:
    return {
        "mas_id": bind.mas_id,
        "spec_revision": bind.spec_revision,
        "runtime_id": bind.runtime_id,
        "deployment_name": bind.deployment_name,
        "bus_kind": bind.bus_kind,
        "agents": [asdict(a) for a in bind.agents],
        "global_infra": dict(bind.global_infra),
    }


def _placement_plan_to_dict(plan, *, mas_id: str, deployment_name: str) -> dict[str, Any]:
    return {
        "apiVersion": "placement/v1",
        "kind": "PlacementPlan",
        "metadata": {
            "mas_id": mas_id,
            "deployment": deployment_name,
            "strategy": plan.strategy,
        },
        "spec": {
            "agents": [
                {
                    "id": a.agent_id,
                    "manifest": a.manifest_path,
                    "placement": {"unit": a.placement_unit},
                    "bind_address": a.bind_address,
                }
                for a in plan.agents
            ],
            "bus": {"kind": plan.bus_kind, "routes": list(plan.routes)},
        },
    }


def compose_run(req: ComposeRequest) -> ComposeResult:
    """Compose application + deployment into ctl artifacts."""
    if req.validate and validation_enabled():
        validate_file(req.manifest, kind="mas").raise_if_failed()

    mas = load_yaml_mapping(req.manifest)
    for ov_path in req.overlay_paths:
        if req.validate and validation_enabled():
            validate_file(ov_path, kind="overlay").raise_if_failed()
        mas = merge_overlay(mas, load_yaml_mapping(ov_path))
    mas_id = mas.get("metadata", {}).get("name") or req.manifest.stem

    workspace = WorkspaceConfig.load(req.manifest.parent)
    user = UserConfig.load()
    merged_refs = merge_infra_refs(
        mas_refs=collect_mas_infra_refs(mas),
        workspace_refs=workspace.effective_infra_refs,
        user_refs=[user.default_infra] if user.default_infra else [],
        cli_refs=list(req.infra_refs),
        workspace_found=workspace.found,
    )
    resolved = resolve_infra_refs(
        merged_refs,
        anchor=req.manifest.parent,
        workspace=workspace,
        user=user,
        interceptors=merge_infra_interceptors(
            mas_interceptors=collect_infra_interceptors(mas),
            workspace_interceptors=workspace.infra_interceptors,
            cli_interceptors=[],
        ),
        mas_config=mas,
    )

    if req.deployment_path:
        if req.validate and validation_enabled():
            validate_file(req.deployment_path, kind="deployment").raise_if_failed()
        deployment = load_yaml_mapping(req.deployment_path)
    else:
        deployment = load_deployment(
            manifest_dir=req.manifest.parent,
            deployment_name=workspace.deployment_name,
        )

    runtime_id = resolve_runtime_id(
        deployment=deployment,
        workspace=workspace,
        cli_override=req.kernel_backend,
    )
    spec = deployment.setdefault("spec", {})
    spec["runtime_id"] = runtime_id

    composed = compose_application(mas, mas_id=mas_id, overlay_ids=req.overlay_ids)
    plan = compose_placement_from_deployment(deployment, composed)
    validate_placement_strategy(plan.strategy)
    bind = compose_effective_bind(
        composed,
        resolved,
        plan,
        deployment_name=deployment.get("metadata", {}).get("name", "local-inproc"),
        mas_base_dir=req.manifest.parent,
    )

    return ComposeResult(
        mas_id=mas_id,
        mas_config=mas,
        effective_bind=_effective_bind_to_dict(bind),
        placement_plan=_placement_plan_to_dict(
            plan,
            mas_id=mas_id,
            deployment_name=deployment.get("metadata", {}).get("name", "local-inproc"),
        ),
        deployment=deployment,
        infra_refs=merged_refs,
        resolved_infra=resolved,
        bind=bind,
        plan=plan,
    )
