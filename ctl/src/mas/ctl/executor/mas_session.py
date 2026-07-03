#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared MAS compose → materialize → session bootstrap (CLI and bench)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mas.ctl.compose.models import EffectiveBindManifest
from mas.ctl.compose.pattern_registry import resolve_design_pattern_registry_id
from mas.ctl.compose.placement_registry import get_placement_backend
from mas.ctl.compose.runner import ComposeResult
from mas.ctl.manifest.mas_agent_merge import enrich_entry_agent_for_delegation, wire_entry_engine_delegation
from mas.ctl.orchestration.sequential import SequentialWorkflow
from mas.ctl.session.controller import ConversationConfig, SessionController
from mas.ctl.ui.turn_result import turn_failed
from mas.runtime.agent_defaults import default_pattern_plugin_id

logger = logging.getLogger(__name__)

RunTurnFn = Callable[[str, str], str]

# Max length for a single-line context value probed as a relative file path.
_MAX_PROBE_PATH_LEN = 512


@dataclass(frozen=True)
class MaterializedMas:
    """Compose output plus materialized runtime instances."""

    compose: ComposeResult
    materialized: Any
    mas_base_dir: Path


@dataclass(frozen=True)
class PreparedEntrySession:
    """Entry agent instance with delegation wiring applied."""

    instance: Any
    enriched_manifest: dict[str, Any]
    manifest_path: Path
    entry_agent_id: str


def entry_agent_id(mas_config: dict[str, Any]) -> str:
    """Resolve the MAS entry agent id from mas config."""
    spec = mas_config.get("spec") or mas_config
    if isinstance(spec.get("entry_agent"), str) and spec["entry_agent"].strip():
        return spec["entry_agent"].strip()
    wf = spec.get("workflow") or {}
    if isinstance(wf, dict) and wf.get("entry"):
        return str(wf["entry"])
    agency = spec.get("agency") or {}
    agents = agency.get("agents") or spec.get("agents") or []
    if agents and isinstance(agents[0], dict):
        return str(agents[0].get("id") or agents[0].get("name") or "agent")
    return "agent"


def agent_manifest_label(manifest: dict[str, Any], manifest_path: Path) -> str:
    """Resolve agent id for observability from OASF agent doc or bench runtime dict."""
    meta = manifest.get("metadata") or {}
    if meta.get("name"):
        return str(meta["name"])
    mas = manifest.get("mas") or {}
    if mas.get("entry_agent"):
        return str(mas["entry_agent"])
    for row in manifest.get("agents") or []:
        if isinstance(row, dict):
            label = row.get("name") or row.get("id")
            if label:
                return str(label)
    resolved = entry_agent_id(manifest)
    if resolved != "agent":
        return resolved
    return manifest_path.stem or "agent"


def workflow_dict(mas_config: dict[str, Any]) -> dict[str, Any]:
    spec = mas_config.get("spec", mas_config)
    wf = spec.get("workflow")
    return wf if isinstance(wf, dict) else {}


def is_sequential_workflow(mas_config: dict[str, Any], num_agents: int) -> bool:
    if num_agents <= 1:
        return False
    wf = workflow_dict(mas_config)
    if not wf:
        return False
    wf_type = str(wf.get("type") or "").lower()
    if wf_type in ("dynamic", "moderated", "broker"):
        return False
    if wf_type in ("sequential", "linear", "pipeline"):
        return True
    return False


def sequential_workflow_payload(mas_config: dict[str, Any]) -> dict[str, Any]:
    wf = workflow_dict(mas_config)
    nodes_raw = wf.get("nodes") or []
    nodes: list[dict[str, str]] = []
    for node in nodes_raw:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        agent = str(node.get("agent") or node_id)
        nodes.append({"id": node_id, "agent": agent, "role": str(node.get("role") or "")})

    edges: list[dict[str, str]] = []
    for edge in wf.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        from_node = edge.get("from") or edge.get("from_node")
        to_node = edge.get("to") or edge.get("to_node")
        if from_node and to_node:
            edges.append({"from": str(from_node), "to": str(to_node)})

    entry = wf.get("entry")
    if not entry and nodes:
        entry = nodes[0]["id"]
    payload = {"entry": str(entry or ""), "nodes": nodes, "edges": edges}
    wf_type = str(wf.get("type") or "").lower()
    if wf_type in ("sequential", "linear", "pipeline") and not edges:
        raise RuntimeError(
            "sequential workflow requires explicit workflow.edges "
            "(delegates_to is not used for sequential routing)"
        )
    return payload


def agent_manifest_path(bind: EffectiveBindManifest, agent_id: str) -> Path | None:
    for agent in bind.agents:
        if agent.agent_id != agent_id:
            continue
        manifest_path = agent.manifest_path
        if not manifest_path:
            return None
        mp = Path(manifest_path)
        if not mp.is_absolute():
            base = bind.mas_base_dir or Path.cwd()
            mp = (base / mp).resolve()
        return mp
    return None


def load_agent_manifest_from_bind(bind: EffectiveBindManifest, agent_id: str) -> dict[str, Any] | None:
    mp = agent_manifest_path(bind, agent_id)
    if mp is None or not mp.is_file():
        return None
    doc = yaml.safe_load(mp.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else None


def resolve_entry_pattern_plugin_id(
    compose: ComposeResult | None,
    entry_id: str,
    *,
    entry_manifest: dict[str, Any] | None = None,
) -> str:
    """Pattern plugin id from compose bind slice, else merged entry manifest."""
    if compose is not None:
        for agent in compose.bind.agents:
            if agent.agent_id == entry_id:
                return agent.pattern_plugin_id
    if entry_manifest:
        spec = entry_manifest.get("spec") or {}
        dp = spec.get("design_pattern")
        if isinstance(dp, dict):
            return resolve_design_pattern_registry_id(dp)
    return default_pattern_plugin_id()


def materialize_mas_compose(compose: ComposeResult, *, mas_base_dir: Path | None = None) -> MaterializedMas:
    base = mas_base_dir or compose.bind.mas_base_dir or Path.cwd()
    materialized = get_placement_backend(compose.plan.strategy).materialize(compose.bind, compose.plan)
    return MaterializedMas(compose=compose, materialized=materialized, mas_base_dir=base)


def prepare_delegation_entry_session(
    materialized: MaterializedMas,
    *,
    entry_id: str,
    entry_manifest: dict[str, Any] | None = None,
    entry_manifest_path: Path | None = None,
    display: Any = None,
    verbose: int = 0,
) -> PreparedEntrySession:
    """Wire dynamic-delegation entry agent (same path as ``execute_run_mas``)."""
    compose = materialized.compose
    instance = materialized.materialized.instances.get(entry_id)
    if instance is None:
        raise KeyError(
            f"entry agent {entry_id!r} not materialized (have: {list(materialized.materialized.instances)})"
        )

    if hasattr(instance.driver, "agent_id"):
        instance.driver.agent_id = entry_id

    manifest_path = entry_manifest_path or agent_manifest_path(compose.bind, entry_id)
    agent_manifest = entry_manifest or load_agent_manifest_from_bind(compose.bind, entry_id) or {}
    entry_manifest_dir = manifest_path.parent if manifest_path else materialized.mas_base_dir

    enriched = enrich_entry_agent_for_delegation(
        agent_manifest,
        compose.mas_config,
        manifest_dir=entry_manifest_dir,
        mas_base_dir=materialized.mas_base_dir,
    )
    wire_entry_engine_delegation(
        getattr(getattr(instance, "driver", None), "engine", None),
        enriched,
        entry_manifest_dir,
        run_turn=make_workflow_send(
            materialized.materialized,
            display=display,
            verbose=verbose,
            from_agent=entry_id,
        ),
        entry_agent_id=entry_id,
        mas_config=compose.mas_config,
        mas_base_dir=materialized.mas_base_dir,
    )
    return PreparedEntrySession(
        instance=instance,
        enriched_manifest=enriched,
        manifest_path=manifest_path or entry_manifest_dir / f"{entry_id}.yaml",
        entry_agent_id=entry_id,
    )


def make_workflow_send(
    materialized: Any,
    *,
    display: Any,
    verbose: int,
    from_agent: str = "",
    obs_setup: Callable[[Any, str], Any] | None = None,
) -> RunTurnFn:
    """Run one agent turn inside a multi-agent workflow (sequential or delegation).

    The returned ``send`` closure holds mutable routing state and is **not reentrant**;
    use one closure per workflow run on a single thread.
    """
    state = {"prev_agent": from_agent, "correlation_id": 0}

    def send(agent_id: str, prompt: str) -> str:
        bus = getattr(materialized, "bus", None)
        prev_agent = state["prev_agent"]
        if bus is not None and prev_agent and prev_agent != agent_id:
            from mas.runtime.schema.egress import InvokeEngineIo

            state["correlation_id"] += 1
            bus.send(
                from_agent=prev_agent,
                to_agent=agent_id,
                intent=InvokeEngineIo(correlation_id=state["correlation_id"], op="TRANSPORT_MSG"),
            )
        instance = materialized.instances.get(agent_id)
        if instance is None:
            raise KeyError(f"agent {agent_id!r} not materialized (have: {list(materialized.instances)})")
        if hasattr(instance.driver, "agent_id"):
            instance.driver.agent_id = agent_id
        sub_display = display
        if from_agent and agent_id != from_agent:
            import sys

            from mas.ctl.ui.stdout import StdoutConversationDisplay

            base = display if isinstance(display, StdoutConversationDisplay) else None
            sub_display = StdoutConversationDisplay(
                out=getattr(base, "_out", sys.stdout),
                err=getattr(base, "_err", sys.stderr),
                agent_label=agent_id,
                verbose=verbose,
                show_labels=True,
                user_prompt_echoed=True,
            )
        obs_rec = obs_setup(instance, agent_id) if obs_setup is not None else None
        controller = SessionController(
            instance=instance,
            display=sub_display,
            verbose=verbose,
            agent_id=agent_id,
            obs_recorder=obs_rec,
            config=ConversationConfig(single_turn=True),
        )
        result = controller.run_turn(prompt)
        if obs_rec is not None:
            from mas.ctl.session.controller import close_observability

            close_observability(controller)
        state["prev_agent"] = agent_id
        if turn_failed(result):
            raise RuntimeError(f"agent {agent_id!r} turn failed")
        return result.text

    return send


def run_sequential_workflow_queries(
    mas_config: dict[str, Any],
    materialized: MaterializedMas,
    queries: list[str],
    *,
    display: Any,
    verbose: int = 0,
    obs_setup: Callable[[Any, str], Any] | None = None,
) -> str:
    """Execute sequential workflow queries; returns final response text."""
    entry = entry_agent_id(mas_config)
    send = make_workflow_send(
        materialized.materialized,
        display=display,
        verbose=verbose,
        from_agent=entry,
        obs_setup=obs_setup,
    )
    wf = SequentialWorkflow.from_dict(sequential_workflow_payload(mas_config), send=send)
    text = ""
    for query in queries:
        wf_result = wf.run(query)
        text = wf_result.content
    return text
