#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``mas-lab serve`` — start the controller daemon HTTP API.

    mas-lab serve
    mas-lab serve --port 8090
    mas-lab serve --ephemeral
    mas-lab serve --jobs-db /tmp/my-jobs.db
"""
from __future__ import annotations

import click


@click.command("serve")
@click.option(
    "--port",
    "-p",
    type=int,
    default=8090,
    show_default=True,
    help="TCP port for the controller HTTP API.",
)
@click.option(
    "--jobs-db",
    type=click.Path(),
    default=None,
    help="SQLite file for durable job persistence (default: ~/.local/share/mas/jobs.db).",
)
@click.option(
    "--ephemeral",
    is_flag=True,
    default=False,
    help="Disable job persistence — jobs live only in memory.",
)
@click.pass_context
def serve_cmd(ctx: click.Context, port: int, jobs_db: str | None, ephemeral: bool) -> None:
    """Launch the MAS Lab controller daemon.

    \b
    Examples
    --------
    mas-lab serve
    mas-lab serve -p 8090
    mas-lab serve --ephemeral
    """
    if jobs_db and ephemeral:
        raise click.UsageError("--jobs-db and --ephemeral are mutually exclusive.")

    click.echo()
    click.echo("=" * 60)
    click.echo("  MAS Lab Serve — controller daemon")
    click.echo("=" * 60)
    click.echo(f"  HTTP       : http://127.0.0.1:{port}")
    if ephemeral:
        click.echo("  Jobs       : ephemeral (in-memory only)")
    elif jobs_db:
        click.echo(f"  Jobs DB    : {jobs_db}")
    else:
        click.echo("  Jobs DB    : <default> (~/.local/share/mas/jobs.db)")
    click.echo()
    click.echo("  Press Ctrl+C to stop")
    click.echo()

    from mas.lab.controller.daemon import main as daemon_main

    argv = ["--port", str(port)]
    if ephemeral:
        argv.append("--ephemeral")
    elif jobs_db:
        argv += ["--jobs-db", jobs_db]

    raise SystemExit(daemon_main(argv))
