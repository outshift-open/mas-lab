#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-ctl compose pipeline — merge application, infra, deployment → EffectiveBind."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mas.ctl.compose.pattern_registry import pattern_for_agent
from mas.ctl.compose.models import (
    AgentBindSlice,
    AgentPlacement,
    ComposedApplication,
    EffectiveBindManifest,
    PlacementPlan,
    ResolvedInfra,
    RuntimeId,
)


def _resolve_plan_runtime(spec: dict) -> RuntimeId:
    from mas.ctl.registry.catalog import validate_runtime_id

    raw = spec.get("runtime_id")
    if isinstance(raw, str) and raw.strip():
        return validate_runtime_id(raw.strip())  # type: ignore[return-value]
    raise ValueError(
        "deployment.spec.runtime_id is required — must be a registered runtime id "
        "(see docs/schemas/component-registry.yaml)"
    )


def compose_application(
    mas_config: dict[str, Any],
    *,
    mas_id: str,
    overlay_ids: list[str] | None = None,
    spec_revision: str = "",
) -> ComposedApplication:
    """Step 1: MAS + overlays (overlay merge done by caller today)."""
    return ComposedApplication(
        mas_id=mas_id,
        config=dict(mas_config),
        spec_revision=spec_revision,
        overlay_ids=list(overlay_ids or []),
    )


def compose_placement_from_deployment(
    deployment: dict[str, Any],
    composed: ComposedApplication,
) -> PlacementPlan:
    """Step 3: deployment manifest → PlacementPlan; agents from MAS if omitted."""
    spec = deployment.get("spec", deployment)
    strategy = spec.get("strategy", "local-inproc")
    framework = spec.get("framework", {})
    bus = spec.get("bus", {})

    agents_cfg = spec.get("agents") or []
    if not agents_cfg:
        agents_cfg = _agents_from_mas(composed.config)

    agents = [
        AgentPlacement(
            agent_id=a["id"],
            manifest_path=a.get("manifest", ""),
            placement_unit=a.get("placement", {}).get("unit", "default"),
            framework_adapter=a.get("framework_adapter", framework.get("default_adapter", "native")),
            bind_address=a.get("bind_address", f"inproc://{a['id']}"),
        )
        for a in agents_cfg
    ]

    return PlacementPlan(
        strategy=strategy,
        runtime_id=_resolve_plan_runtime(spec),
        default_framework_adapter=framework.get("default_adapter", "native"),
        agents=agents,
        bus_kind=bus.get("kind", "inproc"),
        routes=list(bus.get("routes", [])),
    )


def compose_effective_bind(
    composed: ComposedApplication,
    infra: ResolvedInfra,
    plan: PlacementPlan,
    *,
    deployment_name: str = "local-inproc",
    mas_base_dir: Path | None = None,
) -> EffectiveBindManifest:
    """Step 5: final bind manifest for kernel adapters."""
    agents = []
    for placement in plan.agents:
        agents.append(
            AgentBindSlice(
                agent_id=placement.agent_id,
                pattern_plugin_id=pattern_for_agent(
                    composed.config, placement.agent_id, mas_base_dir=mas_base_dir
                ),
                manifest_path=placement.manifest_path or _manifest_path_for_agent(
                    composed.config, placement.agent_id
                ),
                bind_address=placement.bind_address or f"inproc://{placement.agent_id}",
                framework_adapter=placement.framework_adapter,
                llm_ref="infra:llm-proxy",
                tools_ref="infra:tool-registry",
            )
        )

    return EffectiveBindManifest(
        mas_id=composed.mas_id,
        spec_revision=composed.spec_revision,
        runtime_id=plan.runtime_id,
        deployment_name=deployment_name,
        agents=agents,
        bus_kind=plan.bus_kind,
        global_infra={
            "llm_proxy_ref": infra.refs[0] if infra.refs else "",
            "observability_ref": "infra:otel-local",
        },
        composed_application=composed,
        resolved_infra=infra,
        mas_base_dir=mas_base_dir,
    )


def _agents_from_mas(config: dict[str, Any]) -> list[dict[str, str]]:
    spec = config.get("spec", config)
    raw = spec.get("agents") or (spec.get("agency") or {}).get("agents") or []
    out: list[dict[str, str]] = []
    for i, a in enumerate(raw):
        if not isinstance(a, dict):
            out.append({"id": f"agent-{i}"})
            continue
        aid = a.get("name") or a.get("id") or f"agent-{i}"
        entry: dict[str, str] = {"id": aid}
        if a.get("ref"):
            entry["manifest"] = a["ref"]
        out.append(entry)
    return out


def _manifest_path_for_agent(config: dict[str, Any], agent_id: str) -> str:
    spec = config.get("spec", config)
    for entry in (spec.get("agents") or (spec.get("agency") or {}).get("agents") or []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", entry.get("id", ""))
        if name == agent_id:
            return entry.get("manifest") or entry.get("ref") or ""
    return ""


