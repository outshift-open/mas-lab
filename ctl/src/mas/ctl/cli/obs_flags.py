#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared CLI observability overrides — manifest ``spec.observability`` is primary."""

from __future__ import annotations

from typing import Callable

import click

from mas.ctl.adapters.obs.pipeline import ObservabilityConfig
from mas.ctl.session.manifest_config import observability_config_from_manifest


def observability_options(fn: Callable) -> Callable:
    """Optional CLI overrides for manifest-declared observability plugins."""
    fn = click.option(
        "--events/--no-events",
        default=None,
        help="Override manifest observability (on/off)",
    )(fn)
    fn = click.option(
        "--events-file",
        default=None,
        type=click.Path(),
        help="Override JSONL path (default from manifest or traces/events.jsonl)",
    )(fn)
    fn = click.option(
        "--events-stderr",
        "--events-stdout",
        "events_stdout",
        is_flag=True,
        default=False,
        help="Override: also stream transformed events as JSONL on stderr "
        "(keeps stdout clean for the answer). --events-stdout is a legacy alias.",
    )(fn)
    fn = click.option(
        "--events-format",
        default=None,
        type=click.Choice(["native", "boundary", "both", "otel"], case_sensitive=False),
        help="Override transform chain",
    )(fn)
    return fn


def resolve_observability_config(
    *,
    events: bool | None,
    events_file: str | None,
    events_stdout: bool,
    events_format: str | None,
    agent_id: str = "agent",
    manifest: dict | None = None,
    deployment: dict | None = None,
) -> ObservabilityConfig:
    return observability_config_from_manifest(
        manifest,
        deployment=deployment,
        agent_id=agent_id,
        cli_events=events,
        cli_events_file=events_file,
        cli_events_stdout=events_stdout,
        cli_events_format=events_format,
    )
