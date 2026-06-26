#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Checkpoint list/show — ctl persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

import click

from mas.ctl.adapters.checkpoint import JsonCheckpointStore


@click.group("checkpoint")
def checkpoint_group() -> None:
    """Session checkpoint files."""


@checkpoint_group.command("list")
@click.argument("directory", type=click.Path(exists=True))
def list_cmd(directory: str) -> None:
    for path in JsonCheckpointStore(Path(directory)).list_checkpoints():
        click.echo(path.name)


@checkpoint_group.command("show")
@click.argument("path", type=click.Path(exists=True))
def show_cmd(path: str) -> None:
    click.echo(json.dumps(json.loads(Path(path).read_text(encoding="utf-8")), indent=2))
