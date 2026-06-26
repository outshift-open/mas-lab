#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-process controller plugin — satisfies ControllerContract for local dev."""

from __future__ import annotations

from typing import Any, Dict

from mas.lab.contracts.controller import (
    AgentSnapshot,
    ControllerContract,
    DeployResult,
    InfraSnapshot,
)


class LocalInprocController(ControllerContract):
    """Single-process deployment facade (no K8s/Docker orchestrator).

    Tracks agent slots in memory for ``probe()`` / demo UIs. Real execution
    uses ``mas-ctl run-mas`` or ``RuntimeInstance`` in the same OS process.
    """

    name = "local-inproc"
    description = "Local in-process MAS — no external orchestrator."

    def __init__(self) -> None:
        self._agents: Dict[str, AgentSnapshot] = {}

    def probe(self) -> InfraSnapshot:
        agents = list(self._agents.values())
        return InfraSnapshot(
            healthy=True,
            agents=agents,
            capacity={"mode": "local-inproc", "slots": len(agents)},
        )

    def deploy(self, manifest: Dict[str, Any], **kwargs: Any) -> DeployResult:
        meta = manifest.get("metadata") or {}
        agent_id = str(kwargs.get("agent_id") or meta.get("name") or "agent")
        model = ""
        agents = (manifest.get("spec") or {}).get("agents") or []
        if agents and isinstance(agents[0], dict):
            model = str(agents[0].get("llm_model") or "")
        self._agents[agent_id] = AgentSnapshot(
            agent_id=agent_id,
            status="running",
            model=model,
            replicas=int(kwargs.get("replicas", 1)),
        )
        return DeployResult(
            success=True,
            agent_id=agent_id,
            message="deployed in local-inproc controller",
        )

    def scale(self, agent_id: str, replicas: int, **kwargs: Any) -> None:
        snap = self._agents.get(agent_id)
        if snap is not None:
            snap.replicas = replicas

    def configure(self, agent_id: str, config: Dict[str, Any], **kwargs: Any) -> None:
        snap = self._agents.get(agent_id)
        if snap is not None:
            snap.meta.update(config)

    def teardown(self, agent_id: str, **kwargs: Any) -> None:
        self._agents.pop(agent_id, None)
