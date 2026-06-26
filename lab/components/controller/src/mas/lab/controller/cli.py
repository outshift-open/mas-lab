#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""CLI extension — ``mas-lab control`` and ``mas-lab worker`` command groups."""
from __future__ import annotations

import json
import time

import click


@click.group("control")
def control_group() -> None:
    """Controller daemon lifecycle (Unix socket + optional HTTP)."""


@control_group.command("start")
@click.option("--port", "-p", type=int, default=9000, show_default=True, help="HTTP port for UI.")
@click.option("--no-http", is_flag=True, help="IPC only — no HTTP server.")
@click.option("--foreground", "-f", is_flag=True, help="Run daemon in foreground (dev).")
def control_start(port: int, no_http: bool, foreground: bool) -> None:
    """Start the MAS Lab controller daemon."""
    from mas.lab.controller.client import ControllerClient, start_daemon

    client = ControllerClient()
    if client.is_running():
        click.echo("Controller is already running.")
        return
    if foreground:
        import sys

        argv = ["--port", str(port)]
        if no_http:
            argv.append("--no-http")
        from mas.lab.controller.daemon import main

        raise SystemExit(main(argv))
    start_daemon(port=port)
    for _ in range(40):
        if client.is_running():
            click.echo(f"Controller started (HTTP http://127.0.0.1:{port}).")
            return
        time.sleep(0.25)
    click.echo("Controller start initiated — verify with: mas-lab control status")


@control_group.command("stop")
def control_stop() -> None:
    """Stop the controller daemon."""
    from mas.lab.controller.client import stop_daemon

    stop_daemon()
    click.echo("Controller stopped.")


@control_group.command("status")
def control_status() -> None:
    """Show controller daemon status."""
    from mas.lab.controller.client import ControllerClient
    from mas.lab.controller import config as cfg

    client = ControllerClient()
    if not client.is_running():
        click.echo(f"Controller: not running (socket {cfg.socket_path()})")
        raise SystemExit(1)
    info = client.call("status")
    pid_path = cfg.pid_path()
    pid = pid_path.read_text(encoding="utf-8").strip() if pid_path.exists() else "?"
    click.echo(f"Controller: running (pid {pid})")
    click.echo(json.dumps(info, indent=2))


@click.group("worker")
def worker_group() -> None:
    """List and control background workers."""


@worker_group.command("list")
@click.option("--kind", type=click.Choice(["application", "benchmark", "pipeline"]), default=None)
@click.option("--status", default=None)
def worker_list(kind: str | None, status: str | None) -> None:
    """List workers."""
    from mas.lab.controller.client import ControllerClient

    client = ControllerClient()
    client.ensure_running()
    workers = client.call("list_workers", {"kind": kind, "status": status})
    if not workers:
        click.echo("No workers.")
        return
    for w in workers:
        click.echo(f"{w['id']}\t{w['status']}\t{w.get('command', '')}")


@worker_group.command("show")
@click.argument("worker_id")
def worker_show(worker_id: str) -> None:
    """Show worker details."""
    from mas.lab.controller.client import ControllerClient

    client = ControllerClient()
    client.ensure_running()
    detail = client.call("get_worker", {"worker_id": worker_id})
    if detail is None:
        click.secho(f"Worker not found: {worker_id}", fg="red")
        raise SystemExit(1)
    click.echo(json.dumps(detail, indent=2))


@worker_group.command("cancel")
@click.argument("worker_id")
def worker_cancel(worker_id: str) -> None:
    """Cancel a running worker."""
    from mas.lab.controller.client import ControllerClient

    client = ControllerClient()
    client.ensure_running()
    client.call("cancel_worker", {"worker_id": worker_id})
    click.echo(f"Cancel requested for {worker_id}")


@worker_group.command("follow")
@click.argument("worker_id")
@click.option("--interval", type=float, default=0.5, show_default=True,
              help="Poll interval in seconds (REST poll, same as blocking benchmark run).")
def worker_follow(worker_id: str, interval: float) -> None:
    """Follow worker output until completion (polls daemon, streams stdout/stderr)."""
    from mas.lab.controller.client import follow_worker

    try:
        detail = follow_worker(worker_id, poll=interval, stream=True)
    except RuntimeError as exc:
        click.secho(str(exc), fg="red")
        raise SystemExit(1) from exc

    status = detail.get("status")
    click.echo(f"\nWorker {worker_id}: {status} (exit {detail.get('exit_code')})")
    ok = status == "completed" and (detail.get("exit_code") in (0, None))
    raise SystemExit(0 if ok else 1)


class ControllerCliComponent:
    """Entry-point hook for mas.lab.cli.components."""

    def register(self, app: click.Group) -> None:
        app.add_command(control_group, name="control")
        app.add_command(worker_group, name="worker")
