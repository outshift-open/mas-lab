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


def _make_runtime_handler(instance: Any) -> Any:
    """A2A ingress: ``message/send`` → mailbox queue (never ``steer``)."""
    mailbox = SessionTurnMailbox()

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

        def run(text: str) -> Any:
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
def serve_agent_cmd(
    agent: Path,
    overlays: tuple[str, ...],
    infra_refs_cli: tuple[str, ...],
    flavour: str,
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
        try:
            exposure.serve_blocking(manifest, _make_runtime_handler(instance))
        finally:
            if recorder is not None:
                recorder.close()
