#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-ctl chat — stdout conversation UI (ctl owns all display)."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from mas.ctl.cli.help_text import CHAT_EPILOG
from mas.ctl.cli.obs_flags import observability_options, resolve_observability_config
from mas.ctl.cli.trace_flags import mas_ctl_from_configs, resolve_trace_settings, trace_options
from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
from mas.ctl.session.controller import (
    ConversationConfig,
    SessionController,
    close_observability,
    run_session_loop,
)
from mas.ctl.session.display_user_io_contract import ConversationDisplayUserIOContract
from mas.ctl.session.hitl_config import resolve_hitl_from_manifest
from mas.ctl.session.interactive_hitl_contract import InteractiveHitlContract
from mas.ctl.session.observability import setup_observability
from mas.ctl.session.protocol_hints import emit_session_protocol_hints
from mas.ctl.ui.stdout import StdoutConversationDisplay


@click.command("chat", epilog=CHAT_EPILOG)
@click.argument("manifest", required=False, type=click.Path())
@click.option("--prompt", "-p", default=None)
@click.option("--query", "-q", "queries", multiple=True)
@click.option(
    "--interactive/--no-interactive",
    "-i/-I",
    default=None,
    help="Multi-turn REPL (default: TTY unless --single-turn)",
)
@click.option("--single-turn", is_flag=True, help="Exit after first agent reply")
@click.option("-o", "--overlay", "overlays", multiple=True, type=click.Path())
@click.option("--tool", "tools", multiple=True, help="Inline overlay: tool name")
@click.option("--skill", "skills", multiple=True, help="Inline overlay: skill name")
@click.option("--memory", default=None, help="Inline overlay: memory backend id")
@click.option("--set", "set_values", multiple=True, help="Inline overlay: spec.context KEY=VALUE")
@click.option("--pattern", default=None, help="Design pattern plugin id (default from manifest)")
@click.option(
    "--flavour",
    default="local",
    show_default=True,
    help="Deployment flavour from library-standard (only 'local' supported for now)",
)
@click.option(
    "--infra-ref",
    "infra_refs_cli",
    multiple=True,
    help="Infrastructure bundle ref (merged after workspace infra_refs)",
)
@click.option(
    "--runtime-ref",
    "runtime_refs_cli",
    multiple=True,
    help="RuntimeEngine manifest ref (merged after workspace runtime_refs)",
)
@click.option("--memory-seed", "memory_seed_path", default=None, type=click.Path())
@click.option("--checkpoint-dir", default=None, type=click.Path())
@click.option("--load-checkpoint", default=None, type=click.Path())
@click.option("--save-checkpoint/--no-save-checkpoint", default=False)
@click.option("--no-validate", is_flag=True, help="Skip schema validation for seeds/checkpoints")
@click.option(
    "--cache-read/--no-cache-read",
    default=None,
    help="Look up a cached response before calling the LLM "
    "(default: RuntimeEngine cache.read / MAS_LLM_CACHE_READ / true)",
)
@click.option(
    "--cache-write/--no-cache-write",
    default=None,
    help="Persist a response to the cache after calling the LLM "
    "(default: RuntimeEngine cache.write / MAS_LLM_CACHE_WRITE / true)",
)
@click.option(
    "--stream/--no-stream",
    default=None,
    help="Stream the LLM response over SSE instead of waiting for the full "
    "completion (default: RuntimeEngine stream / MAS_LLM_STREAM / false)",
)
@click.option(
    "--without-obs",
    is_flag=True,
    help="Disable envelope observability summand (M_obs) and event recording",
)
@click.option(
    "--without-gov",
    is_flag=True,
    help="Disable governance summand (M_gov), policy evaluation, and HITL chokepoints",
)
@observability_options
@trace_options
@click.option(
    "--model",
    default=None,
    help="Override spec.models for this run (same as MAS_CTL_MODEL)",
)
@click.pass_context
def chat_cmd(
    ctx: click.Context,
    manifest: str | None,
    prompt: str | None,
    queries: tuple[str, ...],
    interactive: bool | None,
    single_turn: bool,
    overlays: tuple[str, ...],
    tools: tuple[str, ...],
    skills: tuple[str, ...],
    memory: str | None,
    set_values: tuple[str, ...],
    pattern: str | None,
    flavour: str,
    infra_refs_cli: tuple[str, ...],
    runtime_refs_cli: tuple[str, ...],
    memory_seed_path: str | None,
    checkpoint_dir: str | None,
    load_checkpoint: str | None,
    save_checkpoint: bool,
    no_validate: bool,
    cache_read: bool | None,
    cache_write: bool | None,
    stream: bool | None,
    without_obs: bool,
    without_gov: bool,
    events: bool | None,
    events_file: str | None,
    events_stdout: bool,
    events_format: str | None,
    trace_mode: str | None,
    no_trace: bool,
    trace_timestamps: bool | None,
    trace_engine: bool,
    trace_summary: bool,
    trace_full: bool,
    trace_color: bool | None,
    model: str | None,
) -> None:
    """Run agent conversation on stdout (You:/Agent: labels).

    Use --help for session commands (/quit, /steer), HITL, and examples.
    """
    from mas.ctl.env import load_dotenv
    from mas.ctl.runtime_cli import load_merged_agent_manifest
    from mas.ctl.session.infra_resolve import resolve_session_infra
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    verbose = int(ctx.obj.get("verbose", 0) if ctx.obj else 0)

    hitl_responder, hitl_terminal = None, None

    from mas.ctl.paths import manifest_cwd, resolve_overlay_path, resolve_path

    with manifest_cwd(manifest, overlay_paths=overlays) as session:
        load_dotenv(cwd=session.original_cwd, manifest_dir=session.manifest_dir)
        workspace = WorkspaceConfig.load(session.manifest_dir or session.original_cwd)
        user = UserConfig.load()
        overlay_strs = tuple(str(p) for p in session.overlays)
        agent_data, plugin = load_merged_agent_manifest(
            session.local_manifest if manifest else None,
            overlays=overlay_strs,
            tools=tools,
            skills=skills,
            memory=memory,
            set_values=set_values,
            pattern=pattern,
            validate=not no_validate,
        )

        from mas.ctl.session.flavour import FlavourError, resolve_flavour

        # Deployment flavour: resolve + validate (only `local` is supported).
        # Surviving deployment concerns (currently: observability plugin
        # selection) are folded in below — see docs/design/flavour-boundary.md.
        try:
            flavour_spec = resolve_flavour(flavour)
        except FlavourError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2) from None

        scripted: list[str] = []
        if prompt:
            scripted.append(prompt)
        scripted.extend(queries)
        if not scripted and not sys.stdin.isatty():
            scripted = [sys.stdin.read().strip()]

        if interactive is None:
            interactive = sys.stdin.isatty() and not single_turn and not scripted
        if single_turn:
            interactive = False

        hitl_responder, hitl_terminal = resolve_hitl_from_manifest(
            agent_data,
            session_interactive=interactive,
        )

        trace = resolve_trace_settings(
            trace_mode=trace_mode,
            no_trace=no_trace,
            trace_summary=trace_summary,
            trace_full=trace_full,
            trace_timestamps=trace_timestamps,
            trace_engine=trace_engine,
            trace_color=trace_color,
            mas_ctl=mas_ctl_from_configs(user.mas_ctl, workspace.mas_ctl),
            verbose=verbose,
        )

        # Built here (not later, where it used to live) so it can also back
        # user_io_contract below -- same instance is reused for the
        # SessionController further down.
        display = StdoutConversationDisplay(
            out=click.get_text_stream("stdout"),
            verbose=verbose,
            show_labels=not interactive,
            user_prompt_echoed=interactive,
            trace=trace.enabled,
        )

        # Agent-initiated HITL (request_human_input)/inform_user() otherwise
        # default to a registry-based contract nothing in an interactive CLI
        # session ever resolves or reads. Give interactive sessions a real
        # resolver/display instead; non-interactive runs keep the default
        # (registry) contracts -- unset here means RegistryHitlContract/
        # RegistryUserIOContract, matching batch/scripted behavior unchanged.
        hitl_contract = InteractiveHitlContract() if interactive else None
        user_io_contract = ConversationDisplayUserIOContract(display) if interactive else None

        def _opt_file(path: str | None) -> Path | None:
            if not path:
                return None
            return resolve_overlay_path(path, orig_cwd=session.original_cwd, manifest_dir=session.manifest_dir)

        def _opt_dir(path: str | None) -> Path | None:
            if not path:
                return None
            return resolve_path(
                path,
                orig_cwd=session.original_cwd,
                manifest_dir=session.manifest_dir,
                expect_dir=True,
                create_dir=True,
            )

        try:
            instance, store = instantiate_runtime(
                InstantiationOptions(
                    pattern_plugin_id=plugin,
                    memory_seed_path=_opt_file(memory_seed_path),
                    checkpoint_path=_opt_file(load_checkpoint),
                    checkpoint_dir=_opt_dir(checkpoint_dir),
                    validate_manifests=not no_validate,
                    cache_read_override=cache_read,
                    cache_write_override=cache_write,
                    stream_override=stream,
                    hitl_contract=hitl_contract,
                    user_io_contract=user_io_contract,
                    agent_manifest=agent_data,
                    manifest_dir=session.manifest_dir if manifest else None,
                    resolved_infra=resolve_session_infra(
                        agent_data,
                        workspace,
                        user,
                        infra_refs_cli=infra_refs_cli,
                        runtime_refs_cli=runtime_refs_cli,
                        anchor=session.manifest_dir or session.original_cwd,
                        with_interceptors=True,
                    ),
                    runtime_refs_cli=runtime_refs_cli,
                    workspace=workspace,
                    enable_observability=not without_obs,
                    enable_governance=not without_gov,
                    model_override=model,
                ),
                hitl=hitl_responder,
            )
        except RuntimeError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(1) from None

        obs_cfg = resolve_observability_config(
            events=events,
            events_file=events_file,
            events_stdout=events_stdout,
            events_format=events_format,
            agent_id="agent",
            manifest=agent_data,
            flavour_spec=flavour_spec,
        )
        obs_rec = setup_observability(
            instance,
            obs_cfg,
            base_dir=session.manifest_dir if manifest else session.original_cwd,
        )

        from mas.ctl.session.session_flags import validate_chat_session

        validate_chat_session(
            interactive=interactive,
            single_turn=single_turn,
            scripted_turns=scripted,
            manifest=agent_data,
        )

        agent_name = agent_data.get("metadata", {}).get("name", "n/a") if agent_data else "n/a"
        if agent_name == "agent" and not manifest:
            # CLI-only run without explicit manifest: show "n/a" instead of generic "agent"
            agent_name = "n/a"

        from mas.runtime.driver.driver import engine_model_id

        llm_name = engine_model_id(getattr(instance.driver, "engine", None))

        controller = SessionController(
            instance=instance,
            display=display,
            hitl_terminal=hitl_terminal,
            checkpoint_store=store,
            verbose=verbose,
            **trace.as_session_kwargs(),
            obs_recorder=obs_rec,
            agent_id=agent_name,
            llm_id=llm_name,
            config=ConversationConfig(
                single_turn=single_turn or (bool(scripted) and not interactive),
                save_checkpoint_each_turn=save_checkpoint,
            ),
        )

        if interactive:
            emit_session_protocol_hints(
                interactive=True,
                hitl_terminal=hitl_terminal,
                hitl_responder=hitl_responder,
                verbose=verbose,
                trace=trace.enabled,
                trace_timestamps=trace.timestamps,
                trace_engine=trace.engine,
            )
        rc = run_session_loop(controller, interactive=interactive, scripted=scripted)

        if save_checkpoint and store is not None:
            path = store.save(instance.record_checkpoint("final"), label="final")
            display.on_system(f"checkpoint saved: {path}")
        close_observability(controller)
        raise SystemExit(rc)
