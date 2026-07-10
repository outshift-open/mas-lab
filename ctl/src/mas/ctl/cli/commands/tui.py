#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-ctl tui — curses UI with same bootstrap as chat."""

from __future__ import annotations

from pathlib import Path

import click

from mas.ctl.cli.obs_flags import observability_options, resolve_observability_config
from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
from mas.ctl.session.hitl_config import resolve_hitl_from_manifest
from mas.ctl.session.observability import setup_observability
from mas.ctl.ui.curses_app import build_curses_controller, run_curses_session


@click.command("tui")
@click.argument("manifest", required=False, type=click.Path())
@click.option("-o", "--overlay", "overlays", multiple=True, type=click.Path())
@click.option("--pattern", default=None)
@click.option(
    "--flavour",
    default="local",
    show_default=True,
    help="Deployment flavour from library-standard (only 'local' supported for now)",
)
@click.option("--single-turn", is_flag=True)
@click.option("--memory-seed", default=None, type=click.Path(exists=True))
@click.option(
    "--infra-ref",
    "--infra",
    "infra_refs_cli",
    multiple=True,
    help="Infrastructure bundle ref",
)
@click.option("--no-validate", is_flag=True)
@observability_options
@click.pass_context
def tui_cmd(
    ctx: click.Context,
    manifest: str | None,
    overlays: tuple[str, ...],
    pattern: str | None,
    flavour: str,
    single_turn: bool,
    memory_seed: str | None,
    infra_refs_cli: tuple[str, ...],
    no_validate: bool,
    events: bool | None,
    events_file: str | None,
    events_stdout: bool,
    events_format: str | None,
) -> None:
    """Curses chat UI — manifest, overlays, infra, and HITL parity with mas-ctl chat."""
    from mas.ctl.env import load_dotenv
    from mas.ctl.paths import manifest_cwd, resolve_overlay_path
    from mas.ctl.runtime_cli import load_merged_agent_manifest
    from mas.ctl.session.infra_resolve import resolve_session_infra
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    hitl_responder, hitl_terminal = None, None

    with manifest_cwd(manifest, overlay_paths=overlays) as session:
        load_dotenv(cwd=session.original_cwd, manifest_dir=session.manifest_dir)
        workspace = WorkspaceConfig.load(session.manifest_dir or session.original_cwd)
        user = UserConfig.load()
        overlay_strs = tuple(str(p) for p in session.overlays)
        agent_data, plugin = load_merged_agent_manifest(
            session.local_manifest if manifest else None,
            overlays=overlay_strs,
            pattern=pattern,
            validate=not no_validate,
        )

        from mas.ctl.session.flavour import FlavourError, validate_flavour

        try:
            validate_flavour(flavour)
        except FlavourError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2) from None

        hitl_responder, _hitl_terminal = resolve_hitl_from_manifest(
            agent_data,
            session_interactive=True,
        )

        def _opt_file(path: str | None) -> Path | None:
            if not path:
                return None
            return resolve_overlay_path(
                path, orig_cwd=session.original_cwd, manifest_dir=session.manifest_dir
            )

        instance, store = instantiate_runtime(
            InstantiationOptions(
                pattern_plugin_id=plugin,
                memory_seed_path=_opt_file(memory_seed),
                validate_manifests=not no_validate,
                agent_manifest=agent_data,
                manifest_dir=session.manifest_dir if manifest else None,
                resolved_infra=resolve_session_infra(
                    agent_data,
                    workspace,
                    user,
                    infra_refs_cli=infra_refs_cli,
                    anchor=session.manifest_dir or session.original_cwd,
                ),
                workspace=workspace,
            ),
            hitl=hitl_responder,
        )

        obs_cfg = resolve_observability_config(
            events=events,
            events_file=events_file,
            events_stdout=events_stdout,
            events_format=events_format,
            agent_id="agent",
            manifest=agent_data,
        )
        obs_rec = setup_observability(
            instance,
            obs_cfg,
            base_dir=session.manifest_dir if manifest else session.original_cwd,
        )

        controller = build_curses_controller(instance, single_turn=single_turn)
        controller.obs_recorder = obs_rec
        controller.config = ConversationConfig(single_turn=single_turn)
        infra_lines = list(infra_refs_cli) or workspace.effective_infra_refs or ["local-inproc"]
        run_curses_session(controller, infra_lines=infra_lines)
        close_observability(controller)
