#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared CLI exchange-tracing flags — see SessionController._setup_exchange_tracing.

Stdout is the human conversation. The exchange log is also for humans (stderr).
Machine consumers use events.jsonl / mas-lab telemetry, not this log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import click

_TRACE_MODES = frozenset({"off", "summary", "full"})


@dataclass(frozen=True)
class TraceSettings:
    """Resolved exchange-log settings for a SessionController."""

    enabled: bool
    summary: bool
    timestamps: bool
    engine: bool
    color: bool

    def as_session_kwargs(self) -> dict[str, bool]:
        return {
            "trace": self.enabled,
            "trace_timestamps": self.timestamps,
            "trace_engine": self.engine,
            "trace_summary": self.summary,
            "trace_color": self.color,
        }


def mas_ctl_from_configs(*sections: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge ``mas_ctl`` maps. Later sections win (user then workspace)."""
    merged: dict[str, Any] = {}
    for section in sections:
        if isinstance(section, Mapping):
            merged.update(section)
    return merged


def _parse_trace_mode(value: Any) -> str | None:
    """Normalize config/CLI values to off|summary|full, or None if unset."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "summary" if value else "off"
    text = str(value).strip().lower()
    if text in ("true", "on", "yes", "1"):
        return "summary"
    if text in ("false", "off", "no", "0", ""):
        return "off"
    if text in _TRACE_MODES:
        return text
    return None


def resolve_trace_settings(
    *,
    trace_mode: str | None = None,
    no_trace: bool = False,
    trace_summary: bool = False,
    trace_full: bool = False,
    trace_timestamps: bool | None = None,
    trace_engine: bool = False,
    trace_color: bool | None = None,
    mas_ctl: Mapping[str, Any] | None = None,
    verbose: int = 0,
) -> TraceSettings:
    """CLI flags override ``config.yaml`` ``mas_ctl``; both override built-ins.

    Built-in when tracing is on: summary + timestamps, color off, engine off
    (engine also follows ``-vv``). Color is never implied by ``--trace``.
    """
    cfg = dict(mas_ctl or {})
    cfg_mode = _parse_trace_mode(cfg.get("trace"))

    if no_trace:
        mode = "off"
    elif isinstance(trace_mode, str) and trace_mode.lower() in ("summary", "full"):
        mode = trace_mode.lower()
    elif trace_full:
        mode = "full"
    elif trace_summary:
        mode = "summary"
    elif cfg_mode:
        mode = cfg_mode
    else:
        mode = "off"

    enabled = mode in ("summary", "full")
    summary = mode == "summary"

    cfg_ts = cfg.get("trace_timestamps")
    if trace_timestamps is not None:
        timestamps = bool(trace_timestamps)
    elif isinstance(cfg_ts, bool):
        timestamps = cfg_ts
    else:
        timestamps = enabled

    cfg_color = cfg.get("trace_color")
    if trace_color is not None:
        color = bool(trace_color)
    elif isinstance(cfg_color, bool):
        color = cfg_color
    else:
        color = False

    cfg_engine = cfg.get("trace_engine")
    engine = bool(trace_engine) or verbose >= 2
    if cfg_engine is True:
        engine = True

    if not enabled:
        timestamps = False
        color = False

    return TraceSettings(
        enabled=enabled,
        summary=summary,
        timestamps=timestamps,
        engine=engine,
        color=color,
    )


def trace_options(fn: Callable) -> Callable:
    """--trace and friends, shared by every command that builds a SessionController."""
    fn = click.option(
        "--trace",
        "trace_mode",
        type=click.Choice(["summary", "full"], case_sensitive=False),
        is_flag=False,
        flag_value="summary",
        default=None,
        help=(
            "Human exchange log on stderr (stdout stays the conversation). "
            "Bare --trace is summary: headers + timestamps. "
            "--trace full dumps payloads. Machines use events.jsonl / telemetry."
        ),
    )(fn)
    fn = click.option(
        "--no-trace",
        is_flag=True,
        help="Disable the exchange log even if config.yaml mas_ctl.trace is set",
    )(fn)
    fn = click.option(
        "--trace-timestamps/--no-trace-timestamps",
        default=None,
        help="UTC timestamp and +elapsed on each exchange (on by default with --trace)",
    )(fn)
    fn = click.option(
        "--trace-engine",
        is_flag=True,
        help="With --trace: raw InvokeEngineIo / EngineIoReturn JSON (also -vv)",
    )(fn)
    fn = click.option(
        "--trace-summary",
        is_flag=True,
        help="Alias for --trace / --trace summary",
    )(fn)
    fn = click.option(
        "--trace-full",
        is_flag=True,
        help="Alias for --trace full (verbose payload dump)",
    )(fn)
    fn = click.option(
        "--trace-color/--no-trace-color",
        default=None,
        help="ANSI color on the exchange log (never the default; opt-in)",
    )(fn)
    return fn
