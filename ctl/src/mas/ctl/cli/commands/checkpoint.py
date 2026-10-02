#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Checkpoint list/show — ctl persistence helpers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import click

from mas.ctl.adapters.checkpoint import JsonCheckpointStore
from mas.runtime.session import ManifestRef


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


@checkpoint_group.command("fork")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--session-id", default=None, help="Explicit identifier for the new fork")
def fork_cmd(path: Path, output_dir: Path | None, session_id: str | None) -> None:
    """Create a new v2 checkpoint branch without changing the source file."""
    source_store = JsonCheckpointStore(path.parent)
    try:
        payload = source_store.load_payload(path)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    if payload.get("version") != 2:
        raise click.ClickException("fork requires a self-contained version 2 checkpoint")

    manifest = payload.get("manifest") or {}
    content = manifest.get("content")
    if not isinstance(content, dict):
        raise click.ClickException("checkpoint manifest content is missing")
    if ManifestRef.from_content(content).content_hash != manifest.get("content_hash"):
        raise click.ClickException("checkpoint manifest hash mismatch")

    parent_lineage = payload["lineage"]
    fork_id = session_id or str(uuid.uuid4())
    payload["lineage"] = {
        "session_id": fork_id,
        "parent_session_id": parent_lineage["session_id"],
        "forked_from_checkpoint": path.name,
        "root_session_id": parent_lineage.get("root_session_id") or parent_lineage["session_id"],
        "created_at": datetime.now(UTC).isoformat(),
    }
    payload["backtrack_count"] = 0
    label = f"fork-{fork_id[:8]}"
    payload["label"] = label
    output_store = JsonCheckpointStore(output_dir or path.parent)
    # Session-id prefix keeps the seed file inside JsonCheckpointStore.retain's glob.
    fork_path = output_store.save(payload, label=f"{fork_id}-{label}")
    click.echo(str(fork_path))


@checkpoint_group.command("resume")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def resume_cmd(ctx: click.Context, path: Path) -> None:
    """Resume a checkpoint using its embedded manifest or CLI chat setup."""
    root = ctx.find_root()
    chat_command = root.command.get_command(root, "chat") if root.command else None
    if chat_command is None:
        raise click.ClickException("chat command is unavailable")
    ctx.invoke(chat_command, manifest=None, load_checkpoint=str(path))
