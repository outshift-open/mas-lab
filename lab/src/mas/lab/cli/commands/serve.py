#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``mas-lab serve`` — start the controller daemon HTTP API.

    mas-lab serve
    mas-lab serve --port 8090
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
@click.pass_context
def serve_cmd(ctx: click.Context, port: int) -> None:
    """Launch the MAS Lab controller daemon.

    \b
    Examples
    --------
    mas-lab serve
    mas-lab serve -p 8090
    """
    click.echo()
    click.echo("=" * 60)
    click.echo("  MAS Lab Serve — controller daemon")
    click.echo("=" * 60)
    click.echo(f"  HTTP       : http://127.0.0.1:{port}")
    click.echo()
    click.echo("  Press Ctrl+C to stop")
    click.echo()

    from mas.lab.controller.daemon import main as daemon_main

    raise SystemExit(daemon_main(["--port", str(port)]))
