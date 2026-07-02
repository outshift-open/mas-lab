#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS run executor — compose, materialize, session (ctl-owned)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.compose.pipeline import compose_application, compose_effective_bind, compose_placement_from_deployment
from mas.ctl.compose.placement_registry import get_placement_backend
from mas.ctl.compose.runner import ComposeRequest, compose_run
from mas.ctl.deployment.runtime_id import DEFAULT_RUNTIME_ID
from mas.ctl.orchestration.sequential import SequentialWorkflow
from mas.ctl.ui.turn_result import turn_failed

logger = logging.getLogger(__name__)


def execute_run_mas(
    manifest: Path,
    *,
    prompt: str | None = None,
    queries: list[str] | None = None,
    overlay_paths: list[Path] | None = None,
    overlay_ids: list[str] | None = None,
    infra_refs: list[str] | None = None,
    deployment_path: Path | None = None,
    kernel_backend: str = DEFAULT_RUNTIME_ID,
    single_turn: bool = False,
    interactive: bool = False,
    auto_hitl: bool = True,
    validate: bool = True,
    verbose: int = 0,
    manifest_dir: Path | None = None,
    obs_config=None,
) -> int:
    """Compose → materialize → workflow or SessionController on entry agent."""
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
    from mas.ctl.session.hitl_config import resolve_hitl_from_manifest
    from mas.ctl.session.observability import setup_observability
    from mas.ctl.session.controller import run_session_loop
    from mas.ctl.ui.stdout import StdoutConversationDisplay

    scripted = list(queries or [])
    if prompt:
        scripted.insert(0, prompt)

    req = ComposeRequest(
        manifest=manifest,
        deployment_path=deployment_path,
        overlay_ids=list(overlay_ids or []),
        overlay_paths=list(overlay_paths or []),
        infra_refs=list(infra_refs or []),
        kernel_backend=kernel_backend,
        validate=validate,
    )
    result = compose_run(req)
    composed = compose_application(result.mas_config, mas_id=result.mas_id)
    plan = compose_placement_from_deployment(result.deployment, composed)
    bind = compose_effective_bind(
        composed,
        result.resolved_infra or ResolvedInfra(refs=result.infra_refs),
        plan,
        deployment_name=result.deployment.get("metadata", {}).get("name", "local-inproc"),
        mas_base_dir=manifest.parent,
    )
    materialized = get_placement_backend(plan.strategy).materialize(bind, plan)

    if getattr(materialized, "bus", None) is not None:
        logger.debug("materialized run has in-process bus with %d routes", len(getattr(materialized.bus, "_endpoints", {}) or {}))

    if interactive and verbose == 0:
        verbose = 1

    base = manifest_dir or manifest.parent

    if _is_sequential_workflow(result.mas_config, len(bind.agents)) and not interactive:
        return _run_sequential_workflow(
            result.mas_config,
            materialized=materialized,
            scripted=scripted,
            verbose=verbose,
            obs_config=obs_config,
            base=base,
        )

    entry = _entry_agent(result.mas_config)
    if not entry and bind.agents:
        entry = bind.agents[0].agent_id
    instance = materialized.instances.get(entry or "")
    if instance is None:
        logger.error("entry agent %r not materialized (have: %s)", entry, list(materialized.instances))
        return 1

    display = StdoutConversationDisplay(
        agent_label=str(entry or "Agent"),
        verbose=verbose,
        show_labels=True,
    )

    if hasattr(instance.driver, "agent_id"):
        instance.driver.agent_id = str(entry or "agent")

    agent_manifest = _load_agent_manifest(bind, str(entry or ""))
    hitl_responder, _ = resolve_hitl_from_manifest(
        agent_manifest,
        session_interactive=interactive or not auto_hitl,
    )
    if hitl_responder is not None:
        instance.driver.hitl = hitl_responder

    obs_rec = None
    if obs_config is not None:
        from dataclasses import replace

        obs_config = replace(obs_config, agent_id=str(entry or "agent"))
        obs_rec = setup_observability(instance, obs_config, base_dir=base)

    controller = SessionController(
        instance=instance,
        display=display,
        verbose=verbose,
        agent_id=str(entry or "agent"),
        obs_recorder=obs_rec,
        config=ConversationConfig(
            single_turn=single_turn or (bool(scripted) and not interactive),
        ),
    )
    exit_code = run_session_loop(
        controller,
        interactive=interactive or not auto_hitl,
        scripted=scripted,
    )
    close_observability(controller)
    if obs_rec is not None and obs_rec.pipeline.emitters:
        from mas.ctl.adapters.obs.emit import JsonlFileEmitter

        for em in obs_rec.pipeline.emitters:
            if isinstance(em, JsonlFileEmitter):
                logger.info("events: %s", em.path)
    return exit_code


def _run_sequential_workflow(
    mas_config: dict[str, Any],
    *,
    materialized: Any,
    scripted: list[str],
    verbose: int,
    obs_config,
    base: Path,
) -> int:
    from mas.ctl.ui.stdout import StdoutConversationDisplay

    task = scripted[0] if scripted else ""
    if not task.strip():
        logger.error("sequential workflow requires a prompt (--prompt or --query)")
        return 1

    display = StdoutConversationDisplay(agent_label="Workflow", verbose=verbose, show_labels=True)
    send = _make_workflow_send(
        materialized,
        display=display,
        verbose=verbose,
        from_agent=_entry_agent(mas_config) or "",
    )
    wf_data = _sequential_workflow_payload(mas_config)
    workflow = SequentialWorkflow.from_dict(wf_data, send=send)
    try:
        wf_result = workflow.run(task)
    except (KeyError, RuntimeError) as exc:
        logger.error("sequential workflow failed: %s", exc)
        return 1
    if wf_result.content.strip():
        display.on_agent(wf_result.content)
    return 0


def _make_workflow_send(
    materialized: Any,
    *,
    display: Any,
    verbose: int,
    from_agent: str = "",
) -> Callable[[str, str], str]:
    from mas.ctl.session.controller import ConversationConfig, SessionController
    from mas.runtime.schema.egress import InvokeEngineIo

    prev_agent = from_agent
    correlation_id = 0

    def send(agent_id: str, prompt: str) -> str:
        nonlocal prev_agent, correlation_id
        bus = getattr(materialized, "bus", None)
        if bus is not None and prev_agent and prev_agent != agent_id:
            correlation_id += 1
            bus.send(
                from_agent=prev_agent,
                to_agent=agent_id,
                intent=InvokeEngineIo(correlation_id=correlation_id, op="TRANSPORT_MSG"),
            )
        instance = materialized.instances.get(agent_id)
        if instance is None:
            raise KeyError(f"agent {agent_id!r} not materialized (have: {list(materialized.instances)})")
        if hasattr(instance.driver, "agent_id"):
            instance.driver.agent_id = agent_id
        controller = SessionController(
            instance=instance,
            display=display,
            verbose=verbose,
            agent_id=agent_id,
            config=ConversationConfig(single_turn=True),
        )
        result = controller.run_turn(prompt)
        prev_agent = agent_id
        if turn_failed(result):
            raise RuntimeError(f"agent {agent_id!r} turn failed")
        return result.text

    return send


def _workflow_dict(mas_config: dict[str, Any]) -> dict[str, Any]:
    spec = mas_config.get("spec", mas_config)
    wf = spec.get("workflow")
    return wf if isinstance(wf, dict) else {}


def _is_sequential_workflow(mas_config: dict[str, Any], num_agents: int) -> bool:
    if num_agents <= 1:
        return False
    wf = _workflow_dict(mas_config)
    if not wf:
        return False
    wf_type = str(wf.get("type") or "").lower()
    if wf_type in ("dynamic", "moderated", "broker"):
        return False
    if wf_type in ("sequential", "linear", "pipeline"):
        return True
    if wf.get("edges"):
        return True
    # Multi-agent with delegates_to but no explicit type defaults to dynamic
    # (entry agent session drives LLM-mediated delegation).
    return False


def _sequential_workflow_payload(mas_config: dict[str, Any]) -> dict[str, Any]:
    wf = _workflow_dict(mas_config)
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

    if not edges:
        for node in nodes_raw:
            if not isinstance(node, dict):
                continue
            from_id = str(node.get("id") or "")
            for target in node.get("delegates_to") or []:
                edges.append({"from": from_id, "to": str(target)})

    entry = wf.get("entry")
    if not entry and nodes:
        entry = nodes[0]["id"]
    return {"entry": str(entry or ""), "nodes": nodes, "edges": edges}


def _entry_agent(mas_config: dict) -> str | None:
    spec = mas_config.get("spec", mas_config)
    if isinstance(spec.get("entry_agent"), str):
        return spec["entry_agent"]
    wf = spec.get("workflow")
    if isinstance(wf, dict) and wf.get("entry"):
        return wf["entry"]
    agency = spec.get("agency") or {}
    agents = agency.get("agents") or spec.get("agents") or []
    if agents and isinstance(agents[0], dict):
        return agents[0].get("name") or agents[0].get("id")
    return None


def _load_agent_manifest(bind: Any, agent_id: str) -> dict | None:
    import yaml

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
        if mp.is_file():
            return yaml.safe_load(mp.read_text(encoding="utf-8"))
    return None
