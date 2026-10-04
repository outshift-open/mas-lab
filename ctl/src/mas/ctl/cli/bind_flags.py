# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""Shared ``--bind`` / ``--override`` wiring for live ctl commands."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import click
from mas.ctl.overrides.bind import combine_overrides

bind_option = click.option(
    "--bind",
    "binds",
    multiple=True,
    metavar="NAME=URI",
    help=(
        "Shortcut for an infra Application or ToolServerRegistry usage: use "
        "row: agent=a2a://host:port/path or tool=mcp://host:port/mcp#name. "
        "Expands to --override infra:…; same merge path as --infra-ref YAML."
    ),
)


def with_binds(
    binds: Sequence[str] | Iterable[str] = (),
    overrides: Sequence[str] | Iterable[str] = (),
) -> tuple[str, ...]:
    """Expand ``--bind`` then append explicit ``--override`` values."""
    return combine_overrides(binds=binds, overrides=overrides)
