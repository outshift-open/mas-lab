#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS run executor — compose, materialize, session (ctl-owned)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

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
    wire_peer_delegation,
)

if TYPE_CHECKING:
    from mas.runtime.boundary.obs.plugins import ObsPluginSet

logger = logging.getLogger(__name__)


def _log_obs_output_paths(plugin_set: "ObsPluginSet") -> None:
    for plugin in plugin_set.plugins:
        get_paths = getattr(plugin, "output_file_paths", None)
        if callable(get_paths):
            for p in get_paths():
                logger.info("events: %s", p)
        else:
            for em in getattr(plugin, "emitters", []):
                path = getattr(em, "path", None)
                if path:
                    logger.info("events: %s", path)


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

    # Wire delegation onto every OTHER agent that declares its own peers too
    # (not just the entry) — see wire_peer_delegation's docstring: without
    # this, an agent that is itself a delegate can never further delegate.
    wire_peer_delegation(
        materialized,
        entry_id=entry,
        display=display,
        verbose=verbose,
        already_wired={entry},
    )

    if runtime_params:
        apply_runtime_params_to_instance(runtime_params, instance)
    hitl_responder, _ = resolve_hitl_from_manifest(
        enriched_manifest,
        session_interactive=interactive or not auto_hitl,
    )
    if hitl_responder is not None:
        instance.driver.hitl = hitl_responder

    from mas.ctl.session.observability import setup_run_observability

    instances = dict(materialized.materialized.instances)
    # Subscribe materialized agents that didn't declare their own
    # spec.observability (see partition_instances_by_observability, FT8) to
    # one shared events.jsonl, not just the entry agent.  Delegated sub-agent
    # turns run through their own SessionController (see make_workflow_send);
    # without a shared plugin set their executions — LLM calls, tools, the
    # whole sub-turn — are never emitted, so delegate_to_* tool calls are
    # opaque black boxes and the multilevel trajectory shows only the
    # moderator.  This mirrors the sequential-workflow path.
    plugin_set, scoped_recorders = setup_run_observability(
        instances, obs_config, base_dir=base, entry_agent_id=str(entry or "agent"),
    )

    controller = SessionController(
        instance=instance,
        display=display,
        verbose=verbose,
        agent_id=str(entry or "agent"),
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
    for recorder in scoped_recorders:
        recorder.close()
    if plugin_set is not None:
        _log_obs_output_paths(plugin_set)
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

    from mas.ctl.session.observability import setup_run_observability

    instances = dict(materialized.materialized.instances)
    entry = entry_agent_id(mas_config)
    shared_plugin_set, scoped_recorders = setup_run_observability(
        instances, obs_config, base_dir=base, entry_agent_id=entry,
    )

    try:
        text = run_sequential_workflow_queries(
            mas_config,
            materialized,
            scripted,
            display=display,
            verbose=verbose,
        )
    except (KeyError, RuntimeError, ValueError) as exc:
        logger.error("sequential workflow failed: %s", exc)
        return 1
    finally:
        if shared_plugin_set is not None:
            shared_plugin_set.close()
        for recorder in scoped_recorders:
            recorder.close()
    if text.strip():
        display.on_agent(text)
    if shared_plugin_set is not None:
        _log_obs_output_paths(shared_plugin_set)
    return 0



def _agent_manifest_path(bind, agent_id: str) -> Path | None:
    from mas.ctl.executor.mas_session import agent_manifest_path

    return agent_manifest_path(bind, agent_id)
