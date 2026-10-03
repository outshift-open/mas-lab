from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from mas.ctl.cli.obs_flags import resolve_observability_config
from mas.ctl.env import load_dotenv
from mas.ctl.infra.resolve import application_endpoint_is_deployed
from mas.ctl.runtime_cli import load_merged_agent_manifest
from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
from mas.ctl.session.flavour import FlavourError, resolve_flavour
from mas.ctl.session.infra_resolve import resolve_session_infra
from mas.ctl.session.observability import setup_observability
from mas.ctl.workspace.config import UserConfig, WorkspaceConfig
from mas.ctl.session.mailbox import SessionTurnMailbox
from mas.runtime.registry import get_registry
from mas.runtime.session import SessionStatus


class _SilentDisplay:
    def on_user(self, text: str, *, turn_id: str = "") -> None:
        return None

    def on_agent(self, text: str) -> None:
        return None

    def on_turn_error(self, message: str, *, detail: str = "") -> None:
        return None

    def on_hitl_request(self, request: Any) -> None:
        return None

    def on_system(self, message: str) -> None:
        return None

    def on_error(self, message: str) -> None:
        return None


def _make_runtime_handler(
    instance: Any,
    *,
    manifest: dict[str, Any] | None = None,
    control_dir: Path | None = None,
) -> Any:
    """A2A ingress: ``message/send`` → mailbox queue (never ``steer``)."""
    from mas.ctl.adapters.checkpoint import InMemoryCheckpointStore
    from mas.ctl.session.control_host import ControlDirectoryHost
    from mas.ctl.session.controller import SessionController
    from mas.ctl.session.manager import SessionManager
    from mas.runtime.boundary.control.contract import ControlCapability, SessionPaused

    manager = SessionManager(checkpoint_store=InMemoryCheckpointStore())
    mailbox = SessionTurnMailbox(queue=manager.turn_queue)
    host: ControlDirectoryHost | None = None
    if control_dir is not None:
        host = ControlDirectoryHost(
            manager.control(capability=ControlCapability(actor="admin", surface="admin")),
            control_dir,
        )

    def ensure_session(session_id: str) -> Any:
        if session_id not in manager.sessions:
            controller = SessionController(instance=instance, display=_SilentDisplay())
            manager.create(instance, controller, manifest or {}, session_id=session_id)
            if host is not None:
                host.advertise(session_id)
        return manager.get(session_id)

    def handle(
        prompt: str,
        *,
        turn_id: str | None = None,
        session_id: str | None = None,
        parent_call_id: str | None = None,
        upstream_correlation_id: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        resolved_session = mailbox.resolve_session_id(session_id)
        session = ensure_session(resolved_session)

        def run(text: str) -> Any:
            if session.status == SessionStatus.PAUSED:
                raise SessionPaused(resolved_session, reason=session.pause_reason)
            return instance.run_user_text(
                text,
                turn_id=turn_id or "u1",
                session_id=resolved_session,
                parent_call_id=parent_call_id or "",
                upstream_correlation_id=upstream_correlation_id,
            )

        trace = mailbox.submit(resolved_session, prompt, source="a2a", run=run)
        text = "\n".join(
            response.content
            for response in trace.client_responses
            if getattr(response, "content", "")
        ).strip()
        stream_chunks = tuple(
            chunk
            for response in trace.client_responses
            for chunk in (getattr(response, "stream_chunks", ()) or ())
        )
        if stream_chunks:
            return stream_chunks
        result: dict[str, Any] = {"text": text, "context_id": resolved_session}
        artifacts = [
            artifact
            for response in trace.client_responses
            for artifact in (getattr(response, "artifacts", ()) or ())
        ]
        if artifacts:
            result["artifacts"] = artifacts
        task_states = [
            response.task_state
            for response in trace.client_responses
            if getattr(response, "task_state", None)
        ]
        if task_states:
            result["task_state"] = task_states[-1]
        if getattr(trace, "awaiting_hitl", False):
            result["task_state"] = "input_required"
        return result

    handle.host = host
    handle.manager = manager
    return handle


@click.command(name="serve")
@click.argument("agent", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--overlay", "overlays", multiple=True, type=click.Path())
@click.option(
    "--infra-ref",
    "infra_refs_cli",
    multiple=True,
    help="Infrastructure manifest/bundle containing the agent's exposed Application endpoint",
)
@click.option("--flavour", default="local", show_default=True)
@click.option(
    "--control-dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Advertise ControlContract so mas-ctl control can attach by A2A contextId "
    "(default: $XDG_RUNTIME_DIR/mas-ctl, else /var/run/mas-ctl, else temp)",
)
@click.option("--no-control", is_flag=True, help="Do not advertise a control endpoint")
def serve_agent_cmd(
    agent: Path,
    overlays: tuple[str, ...],
    infra_refs_cli: tuple[str, ...],
    flavour: str,
    control_dir: Path | None,
    no_control: bool,
) -> None:
    """Serve an agent through the agent_expose plugin selected by its infra endpoint."""
    from mas.ctl.paths import manifest_cwd

    with manifest_cwd(agent, overlay_paths=overlays) as session:
        load_dotenv(cwd=session.original_cwd, manifest_dir=session.manifest_dir)
        workspace = WorkspaceConfig.load(session.manifest_dir or session.original_cwd)
        user = UserConfig.load()
        manifest, pattern_plugin_id = load_merged_agent_manifest(
            session.local_manifest,
            manifest_dir=session.manifest_dir,
            overlays=tuple(str(path) for path in session.overlays),
        )
        if manifest is None:
            raise click.ClickException("serve requires an agent manifest")

        try:
            flavour_spec = resolve_flavour(flavour)
        except FlavourError as error:
            raise click.BadParameter(str(error), param_hint="--flavour") from error

        infra = resolve_session_infra(
            manifest,
            workspace,
            user,
            infra_refs_cli=infra_refs_cli,
            runtime_refs_cli=(),
            anchor=session.manifest_dir or session.original_cwd,
            with_interceptors=True,
        )
        agent_id = str((manifest.get("metadata") or {}).get("name") or "")
        endpoint = infra.applications.get(agent_id)
        if endpoint is None or not application_endpoint_is_deployed(endpoint):
            raise click.ClickException(
                f"No deployed infra Application endpoint named {agent_id!r}; set usage: deploy "
                "or usage: use-and-deploy "
                "in workspace infra_refs or pass --infra-ref"
            )

        instance, _ = instantiate_runtime(
            InstantiationOptions(
                pattern_plugin_id=pattern_plugin_id,
                agent_manifest=manifest,
                manifest_dir=session.manifest_dir,
                resolved_infra=infra,
                workspace=workspace,
            )
        )
        obs_config = resolve_observability_config(
            events=None,
            events_file=None,
            events_stdout=False,
            events_format=None,
            agent_id=agent_id,
            manifest=manifest,
            flavour_spec=flavour_spec,
        )
        recorder = setup_observability(
            instance,
            obs_config,
            base_dir=session.manifest_dir or session.original_cwd,
        )
        exposure = get_registry().create(
            "agent_expose",
            binding={"type": endpoint["protocol"]},
            endpoint=endpoint,
        )
        from mas.ctl.session.control_dir import default_control_dir

        handler = _make_runtime_handler(
            instance,
            manifest=manifest,
            control_dir=None if no_control else (control_dir or default_control_dir()),
        )
        try:
            exposure.serve_blocking(manifest, handler)
        finally:
            host = getattr(handler, "host", None)
            if host is not None:
                host.close()
            if recorder is not None:
                recorder.close()
