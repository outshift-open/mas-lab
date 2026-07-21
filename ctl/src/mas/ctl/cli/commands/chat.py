#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-ctl chat — stdout conversation UI (ctl owns all display)."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
from mas.ctl.cli.obs_flags import observability_options, resolve_observability_config
from mas.ctl.session.controller import (
    ConversationConfig,
    SessionController,
    close_observability,
    run_session_loop,
)
from mas.ctl.session.hitl_config import resolve_hitl_from_manifest
from mas.ctl.session.observability import setup_observability
from mas.ctl.cli.help_text import CHAT_EPILOG
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
    help="Infrastructure bundle ref (merged after workspace + MAS spec.infra_refs)",
)
@click.option("--memory-seed", "memory_seed_path", default=None, type=click.Path())
@click.option("--checkpoint-dir", default=None, type=click.Path())
@click.option("--load-checkpoint", default=None, type=click.Path())
@click.option("--save-checkpoint/--no-save-checkpoint", default=False)
@click.option("--no-validate", is_flag=True, help="Skip schema validation for seeds/checkpoints")
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
@click.option(
    "--trace",
    is_flag=True,
    help="Stream AGENT↔LLM↔TOOL exchanges on stderr as they happen",
)
@click.option(
    "--trace-timestamps",
    is_flag=True,
    help="With --trace: UTC timestamp and +elapsed on each exchange",
)
@click.option(
    "--trace-engine",
    is_flag=True,
    help="With --trace: raw InvokeEngineIo / EngineIoReturn JSON (also -vv)",
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
    memory_seed_path: str | None,
    checkpoint_dir: str | None,
    load_checkpoint: str | None,
    save_checkpoint: bool,
    no_validate: bool,
    without_obs: bool,
    without_gov: bool,
    events: bool | None,
    events_file: str | None,
    events_stdout: bool,
    events_format: str | None,
    trace: bool,
    trace_timestamps: bool,
    trace_engine: bool,
) -> None:
    """Run agent conversation on stdout (You:/Agent: labels).

    Use --help for session commands (/quit, /steer), HITL, and examples.
    """
    from mas.ctl.env import load_dotenv
    from mas.ctl.session.infra_resolve import resolve_session_infra
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig
    from mas.ctl.runtime_cli import load_merged_agent_manifest

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

        def _opt_file(path: str | None) -> Path | None:
            if not path:
                return None
            return resolve_overlay_path(
                path, orig_cwd=session.original_cwd, manifest_dir=session.manifest_dir
            )

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
                    agent_manifest=agent_data,
                    manifest_dir=session.manifest_dir if manifest else None,
                    resolved_infra=resolve_session_infra(
                        agent_data,
                        workspace,
                        user,
                        infra_refs_cli=infra_refs_cli,
                        anchor=session.manifest_dir or session.original_cwd,
                        with_interceptors=True,
                    ),
                    workspace=workspace,
                    enable_observability=not without_obs,
                    enable_governance=not without_gov,
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

        display = StdoutConversationDisplay(
            out=click.get_text_stream("stdout"),
            verbose=verbose,
            show_labels=not interactive,
            user_prompt_echoed=interactive,
        )
        controller = SessionController(
            instance=instance,
            display=display,
            hitl_terminal=hitl_terminal,
            checkpoint_store=store,
            verbose=verbose,
            trace=trace,
            trace_timestamps=trace_timestamps,
            trace_engine=trace_engine or verbose >= 2,
            obs_recorder=obs_rec,
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
                trace=trace,
                trace_timestamps=trace_timestamps,
                trace_engine=trace_engine or verbose >= 2,
            )
        rc = run_session_loop(controller, interactive=interactive, scripted=scripted)

        if save_checkpoint and store is not None:
            path = store.save(instance.record_checkpoint("final"), label="final")
            display.on_system(f"checkpoint saved: {path}")
        close_observability(controller)
        raise SystemExit(rc)
