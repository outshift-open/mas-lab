#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Attach to a live session by the same id A2A exposes as contextId."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from mas.library.standard.plugins.control.attach import HostGone, attach
from mas.library.standard.plugins.control.directory import FileSessionDirectory
from mas.library.standard.plugins.control.script import (
    parse_control_chain,
    parse_control_script,
    parse_queue_at,
    resolve_curl_data,
)
from mas.runtime.boundary.control.contract import SessionBusy, SessionNotStopped


class ControlCLI(click.Group):
    """``mas-ctl control SESSION pause persist`` is the same as a script file."""

    def resolve_command(self, ctx: click.Context, args: list[str]):
        if args and args[0] not in self.commands and not str(args[0]).startswith("-"):
            return super().resolve_command(ctx, ["script", *args])
        return super().resolve_command(ctx, args)


@click.group("control", cls=ControlCLI)
@click.option(
    "--directory",
    "-d",
    "directory",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Control directory advertised by chat/serve "
    "(default: $XDG_RUNTIME_DIR/mas-ctl, else /var/run/mas-ctl, else temp)",
)
@click.pass_context
def control_group(ctx: click.Context, directory: Path | None) -> None:
    """Attach to ControlContract using the session id (A2A contextId)."""
    from mas.ctl.session.control_dir import default_control_dir

    ctx.ensure_object(dict)
    ctx.obj["control_dir"] = directory or default_control_dir()


def _echo(value: Any) -> None:
    if value is None:
        return
    click.echo(json.dumps(value, indent=2, default=str))


def _run(directory: Path, session_id: str, call: Any) -> Any:
    async def go() -> Any:
        client = await attach(FileSessionDirectory(directory), session_id)
        try:
            return await call(client)
        finally:
            await client.close()

    try:
        return asyncio.run(go())
    except HostGone as exc:
        raise click.ClickException(str(exc)) from exc
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    except SessionBusy as exc:
        raise click.ClickException(f"{exc}; retry with --after") from exc
    except SessionNotStopped as exc:
        raise click.ClickException(f"{exc}") from exc


async def _arun_statements(client: Any, session_id: str, statements: Any, *, auto_stop: bool) -> list[Any]:
    run_script = getattr(client, "arun_script", None)
    if callable(run_script):
        body = "\n".join(item.raw for item in statements)
        result = await run_script(session_id, text=body, auto_stop=auto_stop)
        return list(result or [])
    results: list[Any] = []
    for statement in statements:
        verb = statement.verb
        kwargs = dict(statement.kwargs)
        if verb in {"attach", "inspect", "info"}:
            results.append(await client.ainspect(session_id))
            continue
        if verb == "pause":
            await client.apause(session_id, reason=str(kwargs.get("reason") or "operator"))
            results.append({"paused": session_id})
            continue
        if verb == "resume":
            await client.aresume(session_id)
            results.append({"resumed": session_id})
            continue
        if verb == "snapshot":
            results.append(
                await client.asnapshot(
                    session_id,
                    label=str(kwargs.get("label") or ""),
                    auto_stop=bool(kwargs.get("auto_stop", auto_stop)),
                )
            )
            continue
        if verb == "persist":
            extra = {
                "label": str(kwargs.get("label") or ""),
                "auto_stop": bool(kwargs.get("auto_stop", auto_stop)),
            }
            if kwargs.get("snapshot_id"):
                extra["snapshot_id"] = str(kwargs["snapshot_id"])
            results.append(await client.apersist(session_id, **extra))
            continue
        if verb == "checkpoints":
            results.append(await client.alist_checkpoints(session_id))
            continue
        if verb == "steer":
            if kwargs.get("replace") and (kwargs.get("after") or kwargs.get("enqueue")):
                raise ValueError("steer: use --replace or --after, not both")
            if kwargs.get("replace"):
                mode = "replace"
            elif kwargs.get("after") or kwargs.get("enqueue"):
                mode = "after"
            else:
                mode = "preempt"
            await client.asteer(
                session_id,
                text=str(kwargs.get("text") or ""),
                mode=mode,
                at=parse_queue_at(kwargs.get("at", "head")),
            )
            results.append({"steered": session_id, "mode": mode, "at": kwargs.get("at", "head")})
            continue
        if verb in {"enqueue", "enqueue_input"}:
            queued = await client.aenqueue_input(
                session_id,
                text=str(kwargs.get("text") or ""),
                source=str(kwargs.get("source") or "cli"),
                action=str(kwargs.get("action") or "turn"),
                at=parse_queue_at(kwargs.get("at", "tail")),
            )
            results.append({"enqueued": queued, "at": kwargs.get("at", "tail")})
            continue
        raise click.ClickException(f"unknown control command {verb!r}")
    return results


@control_group.command("script")
@click.argument("session_id")
@click.option(
    "--data",
    "data",
    default=None,
    help="curl-style body: @file or inline text (same language as chained argv)",
)
@click.option("-e", "--eval", "evals", multiple=True, help="Inline command (repeatable)")
@click.option("-f", "--file", "script_file", default=None, type=click.Path(), help="Script file")
@click.option("--auto-stop", is_flag=True, help="Pause before snapshot/persist if still running")
@click.argument("chain", nargs=-1)
@click.pass_context
def script_cmd(
    ctx: click.Context,
    session_id: str,
    data: str | None,
    evals: tuple[str, ...],
    script_file: str | None,
    auto_stop: bool,
    chain: tuple[str, ...],
) -> None:
    """Run a control script. Chained argv, ``-e``, ``-f``, and ``--data @file`` are equivalent."""
    from mas.library.standard.plugins.control.script import ControlStatement

    statements: list[ControlStatement] = []
    if script_file:
        statements.extend(parse_control_script(resolve_curl_data(f"@{script_file}")))
    if data:
        statements.extend(parse_control_script(resolve_curl_data(data)))
    for item in evals:
        statements.extend(parse_control_script(resolve_curl_data(item)))
    if chain:
        statements.extend(parse_control_chain(list(chain)))
    if not statements:
        raise click.ClickException("no control commands; pass a chain, -e, -f, or --data")
    directory: Path = ctx.obj["control_dir"]
    results = _run(
        directory,
        session_id,
        lambda client: _arun_statements(client, session_id, statements, auto_stop=auto_stop),
    )
    _echo(results)


@control_group.command("attach")
@click.argument("session_id")
@click.pass_context
def attach_cmd(ctx: click.Context, session_id: str) -> None:
    """Resolve SESSION_ID in the directory and print inspect()."""
    directory: Path = ctx.obj["control_dir"]
    view = _run(directory, session_id, lambda client: client.ainspect(session_id))
    click.echo(json.dumps(view, indent=2))


@control_group.command("inspect")
@click.argument("session_id")
@click.pass_context
def inspect_cmd(ctx: click.Context, session_id: str) -> None:
    directory: Path = ctx.obj["control_dir"]
    view = _run(directory, session_id, lambda client: client.ainspect(session_id))
    click.echo(json.dumps(view, indent=2))


@control_group.command("pause")
@click.argument("session_id")
@click.option("--reason", default="operator")
@click.pass_context
def pause_cmd(ctx: click.Context, session_id: str, reason: str) -> None:
    directory: Path = ctx.obj["control_dir"]
    _run(directory, session_id, lambda client: client.apause(session_id, reason=reason))
    click.echo(f"paused {session_id}")


@control_group.command("resume")
@click.argument("session_id")
@click.pass_context
def resume_cmd(ctx: click.Context, session_id: str) -> None:
    directory: Path = ctx.obj["control_dir"]
    _run(directory, session_id, lambda client: client.aresume(session_id))
    click.echo(f"resumed {session_id}")


@control_group.command("snapshot")
@click.argument("session_id")
@click.option("--label", default="control")
@click.option("--auto-stop", is_flag=True, help="Pause first if the session is still running")
@click.pass_context
def snapshot_cmd(ctx: click.Context, session_id: str, label: str, auto_stop: bool) -> None:
    directory: Path = ctx.obj["control_dir"]
    ref = _run(
        directory,
        session_id,
        lambda client: client.asnapshot(session_id, label=label, auto_stop=auto_stop),
    )
    click.echo(json.dumps(ref, indent=2))


@control_group.command("checkpoints")
@click.argument("session_id")
@click.pass_context
def checkpoints_cmd(ctx: click.Context, session_id: str) -> None:
    directory: Path = ctx.obj["control_dir"]
    nodes = _run(directory, session_id, lambda client: client.alist_checkpoints(session_id))
    click.echo(json.dumps(nodes, indent=2))


@control_group.command("persist")
@click.argument("session_id")
@click.option("--snapshot-id", default=None, help="In-memory snapshot id; default takes a new one")
@click.option("--label", default="persist")
@click.option("--auto-stop", is_flag=True, help="Pause first if the session is still running")
@click.pass_context
def persist_cmd(
    ctx: click.Context,
    session_id: str,
    snapshot_id: str | None,
    label: str,
    auto_stop: bool,
) -> None:
    """Write a self-contained checkpoint file for later mas-ctl chat --load-checkpoint."""
    directory: Path = ctx.obj["control_dir"]
    kwargs: dict[str, Any] = {"label": label, "auto_stop": auto_stop}
    if snapshot_id:
        kwargs["snapshot_id"] = snapshot_id
    result = _run(
        directory,
        session_id,
        lambda client: client.apersist(session_id, **kwargs),
    )
    click.echo(json.dumps(result, indent=2))


@control_group.command("steer")
@click.argument("session_id")
@click.option("--text", required=True)
@click.option(
    "--replace",
    is_flag=True,
    help="Discard streamed tokens and start a new turn",
)
@click.option(
    "--after",
    "after",
    is_flag=True,
    help="Do not interrupt; queue to the front and wait for this generation to finish",
)
@click.option(
    "--enqueue",
    is_flag=True,
    help="Alias of --after",
)
@click.option(
    "--at",
    default="head",
    help="Placement when waiting (--after): tail, head (default), or an inspect_queue index",
)
@click.pass_context
def steer_cmd(
    ctx: click.Context,
    session_id: str,
    text: str,
    replace: bool,
    after: bool,
    enqueue: bool,
    at: str,
) -> None:
    directory: Path = ctx.obj["control_dir"]
    if replace and (after or enqueue):
        raise click.UsageError("use --replace or --after, not both")
    if replace:
        mode = "replace"
    elif after or enqueue:
        mode = "after"
    else:
        mode = "preempt"
    parsed_at = parse_queue_at(at)
    _run(
        directory,
        session_id,
        lambda client: client.asteer(session_id, text=text, mode=mode, at=parsed_at),
    )
    click.echo(f"steered {session_id} ({mode} at={parsed_at})")
