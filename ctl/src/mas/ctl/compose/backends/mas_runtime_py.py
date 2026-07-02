#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Default OSS Python runtime — RuntimeInstance from EffectiveBind + resolved infra."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mas.ctl.compose.models import AgentBindSlice, EffectiveBindManifest, KernelBackendId, ResolvedInfra
from mas.ctl.deployment.runtime_id import DEFAULT_RUNTIME_ID
from mas.runtime.driver.instance import RuntimeInstance


@dataclass
class MaterializedLocal:
    instances: dict[str, RuntimeInstance] = field(default_factory=dict)
    infra: ResolvedInfra | None = None


class MasRuntimePyKernelBackend:
    backend_id: KernelBackendId = DEFAULT_RUNTIME_ID  # type: ignore[assignment]

    def __init__(self, *, resolved_infra: ResolvedInfra | None = None) -> None:
        self._infra = resolved_infra

    def create_agent_runtime(self, bind: EffectiveBindManifest, agent_id: str) -> RuntimeInstance:
        from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime

        slice_ = _find_agent(bind, agent_id)
        manifest_path = slice_.manifest_path
        agent_manifest: dict | None = None
        manifest_dir = bind.mas_base_dir or Path.cwd()
        if manifest_path:
            import yaml

            mp = Path(manifest_path)
            if not mp.is_absolute():
                base = bind.mas_base_dir or Path.cwd()
                mp = (base / mp).resolve()
            if mp.is_file():
                agent_manifest = yaml.safe_load(mp.read_text(encoding="utf-8"))
                manifest_dir = mp.parent
                if agent_manifest:
                    from mas.ctl.manifest.spec_bindings import parse_collaboration
                    from mas.runtime.engine.tools import resolve_manifest_tool_refs

                    parse_collaboration((agent_manifest.get("spec") or {}).get("collaboration"))
                    agent_manifest = resolve_manifest_tool_refs(agent_manifest, manifest_dir)

        instance, _ = instantiate_runtime(
            InstantiationOptions(
                pattern_plugin_id=slice_.pattern_plugin_id,
                agent_manifest=agent_manifest,
                manifest_dir=manifest_dir,
                resolved_infra=self._infra or ResolvedInfra(),
            ),
        )
        instance.driver.agent_id = agent_id
        return instance

    def materialize(
        self,
        bind: EffectiveBindManifest,
        plan,
        *,
        resolved_infra: ResolvedInfra | None = None,
    ) -> MaterializedLocal:
        infra = resolved_infra or self._infra
        backend = MasRuntimePyKernelBackend(resolved_infra=infra)
        instances = {a.agent_id: backend.create_agent_runtime(bind, a.agent_id) for a in bind.agents}
        return MaterializedLocal(instances=instances, infra=infra)


def _find_agent(bind: EffectiveBindManifest, agent_id: str) -> AgentBindSlice:
    for agent in bind.agents:
        if agent.agent_id == agent_id:
            return agent
    raise KeyError(f"agent {agent_id!r} not in effective bind")
