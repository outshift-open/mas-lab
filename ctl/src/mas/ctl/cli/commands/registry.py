#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-ctl registry — list and query runtime + ctl components."""

from __future__ import annotations

import json

import click

from mas.ctl.registry import query_registry


@click.group("registry")
def registry_group() -> None:
    """List/query runtime machines, ctl registries, and schema kinds."""


@registry_group.command("list")
@click.option("--layer", "-l", default=None, help="Filter by layer prefix")
@click.option("--json", "as_json", is_flag=True)
def list_cmd(layer: str | None, as_json: bool) -> None:
    """List all registered components."""
    entries = query_registry(layer=layer)
    if as_json:
        click.echo(json.dumps([e.__dict__ for e in entries], indent=2))
        return
    current = ""
    for e in entries:
        if e.layer != current:
            current = e.layer
            click.echo(f"\n[{current}]")
        click.echo(f"  {e.id}  {e.description}")


@registry_group.command("query")
@click.argument("id_prefix")
@click.option("--layer", "-l", default=None)
@click.option("--json", "as_json", is_flag=True)
def query_cmd(id_prefix: str, layer: str | None, as_json: bool) -> None:
    """Query components by id prefix."""
    entries = query_registry(layer=layer, id_prefix=id_prefix)
    if as_json:
        click.echo(json.dumps([e.__dict__ for e in entries], indent=2))
        return
    for e in entries:
        click.echo(f"{e.layer}\t{e.id}\t{e.description}")
