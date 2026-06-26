#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Compose pipeline models — mas-ctl output types (bind/v1, deployment/v1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


KernelBackendId = Literal["python-v2"]
RuntimeId = KernelBackendId
DeploymentStrategy = Literal["local-inproc", "local-multiprocess", "docker", "kubernetes"]
FrameworkAdapterId = Literal["native", "langgraph", "crewai"]
BusKind = Literal["inproc", "unix", "grpc", "k8s"]


@dataclass
class ComposedApplication:
    """MAS + overlays merged — ctl step 1 output."""

    mas_id: str
    config: dict[str, Any]
    spec_revision: str = ""
    overlay_ids: list[str] = field(default_factory=list)


@dataclass
class ResolvedInfra:
    """Infra refs resolved — ctl step 2 output."""

    refs: list[str] = field(default_factory=list)
    llm_proxy: dict[str, Any] = field(default_factory=dict)
    tool_registry: dict[str, Any] = field(default_factory=dict)
    tool_server_registry: dict[str, Any] = field(default_factory=dict)
    observability: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentPlacement:
    agent_id: str
    manifest_path: str = ""
    placement_unit: str = "default"
    framework_adapter: FrameworkAdapterId = "native"
    bind_address: str = ""


@dataclass
class PlacementPlan:
    """Deployment manifest materialization — ctl step 3."""

    strategy: DeploymentStrategy = "local-inproc"
    runtime_id: RuntimeId = "python-v2"
    default_framework_adapter: FrameworkAdapterId = "native"
    agents: list[AgentPlacement] = field(default_factory=list)
    bus_kind: BusKind = "inproc"
    routes: list[dict[str, str]] = field(default_factory=list)


@dataclass
class AgentBindSlice:
    agent_id: str
    pattern_plugin_id: str = "react@v1"
    manifest_path: str = ""
    bind_address: str = ""
    framework_adapter: FrameworkAdapterId = "native"
    llm_ref: str = ""
    tools_ref: str = ""


@dataclass
class EffectiveBindManifest:
    """Generated bind artifact — sole input to kernel adapter."""

    mas_id: str
    spec_revision: str
    runtime_id: RuntimeId
    deployment_name: str
    agents: list[AgentBindSlice] = field(default_factory=list)
    bus_kind: BusKind = "inproc"
    global_infra: dict[str, str] = field(default_factory=dict)
    composed_application: ComposedApplication | None = None
    resolved_infra: ResolvedInfra | None = None
    mas_base_dir: Path | None = None
