#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS run executor — compose, materialize, session (ctl-owned)."""

from __future__ import annotations

import logging
from pathlib import Path

from mas.ctl.compose.runner import ComposeRequest, compose_run
from mas.ctl.deployment.runtime_id import DEFAULT_RUNTIME_ID
from mas.ctl.executor.mas_session import (
    entry_agent_id,
    is_sequential_workflow,
    load_agent_manifest_from_bind,
    make_workflow_send,
    materialize_mas_compose,
    prepare_delegation_entry_session,
    run_sequential_workflow_queries,
)

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
    from mas.ctl.session.params_sidecar import (
        apply_runtime_params_to_instance,
        params_from_mas_config,
        stage_runtime_params,
    )

    runtime_params = params_from_mas_config(result.mas_config)
    if runtime_params:
        stage_runtime_params(runtime_params)

    bind = result.bind
    materialized = materialize_mas_compose(result, mas_base_dir=manifest_dir or manifest.parent)

    if getattr(materialized.materialized, "bus", None) is not None:
        logger.debug(
            "materialized run has in-process bus with %d routes",
            len(getattr(materialized.materialized.bus, "_endpoints", {}) or {}),
        )

    if interactive and verbose == 0:
        verbose = 1

    base = manifest_dir or manifest.parent

    if is_sequential_workflow(result.mas_config, len(bind.agents)) and not interactive:
        return _run_sequential_workflow(
            result.mas_config,
            materialized=materialized,
            scripted=scripted,
            verbose=verbose,
            obs_config=obs_config,
            base=base,
        )

    entry = entry_agent_id(result.mas_config)
    display = StdoutConversationDisplay(
        agent_label=str(entry or "Agent"),
        verbose=verbose,
        show_labels=True,
    )

    try:
        prepared = prepare_delegation_entry_session(
            materialized,
            entry_id=entry,
            display=display,
            verbose=verbose,
        )
    except KeyError as exc:
        logger.error("%s", exc)
        return 1

    instance = prepared.instance
    enriched_manifest = prepared.enriched_manifest

    if runtime_params:
        apply_runtime_params_to_instance(runtime_params, instance)
    hitl_responder, _ = resolve_hitl_from_manifest(
        enriched_manifest,
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
    mas_config: dict,
    *,
    materialized,
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

    def _obs_setup(instance: object, agent_id: str):
        if obs_config is None:
            return None
        from dataclasses import replace

        from mas.ctl.session.observability import setup_observability

        cfg = replace(obs_config, agent_id=agent_id)
        return setup_observability(instance, cfg, base_dir=base)

    try:
        text = run_sequential_workflow_queries(
            mas_config,
            materialized,
            scripted,
            display=display,
            verbose=verbose,
            obs_setup=_obs_setup if obs_config is not None else None,
        )
    except (KeyError, RuntimeError, ValueError) as exc:
        logger.error("sequential workflow failed: %s", exc)
        return 1
    if text.strip():
        display.on_agent(text)
    return 0


# Backward-compatible re-exports for tests and internal callers.
_is_sequential_workflow = is_sequential_workflow
_entry_agent = entry_agent_id
_make_workflow_send = make_workflow_send
_load_agent_manifest = load_agent_manifest_from_bind


def _sequential_workflow_payload(mas_config: dict) -> dict:
    from mas.ctl.executor.mas_session import sequential_workflow_payload

    return sequential_workflow_payload(mas_config)


def _agent_manifest_path(bind, agent_id: str) -> Path | None:
    from mas.ctl.executor.mas_session import agent_manifest_path

    return agent_manifest_path(bind, agent_id)
