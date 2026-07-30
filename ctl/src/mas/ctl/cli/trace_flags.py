#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared CLI exchange-tracing flags — see SessionController._setup_exchange_tracing."""

from __future__ import annotations

from typing import Callable

import click


def trace_options(fn: Callable) -> Callable:
    """--trace and friends, shared by every command that builds a SessionController."""
    fn = click.option(
        "--trace",
        is_flag=True,
        help="Stream AGENT↔LLM↔TOOL exchanges on stderr as they happen",
    )(fn)
    fn = click.option(
        "--trace-timestamps",
        is_flag=True,
        help="With --trace: UTC timestamp and +elapsed on each exchange",
    )(fn)
    fn = click.option(
        "--trace-engine",
        is_flag=True,
        help="With --trace: raw InvokeEngineIo / EngineIoReturn JSON (also -vv)",
    )(fn)
    fn = click.option(
        "--trace-summary",
        is_flag=True,
        help="With --trace: only print exchange headers (AGENT→LLM, LLM→AGENT, etc)",
    )(fn)
    fn = click.option(
        "--trace-color",
        is_flag=True,
        help="With --trace: colorize output (gray=timestamp, cyan=header, yellow=metadata, white=content)",
    )(fn)
    return fn
