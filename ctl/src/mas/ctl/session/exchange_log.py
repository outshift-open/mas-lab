#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Format AGENT↔LLM↔TOOL exchange lines for CLI trace output."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from typing import Any

from mas.runtime.driver.driver import DriverTrace, ExchangeRecord

logger = logging.getLogger("mas.runtime")


@dataclass(frozen=True)
class TraceFormatOptions:
    timestamps: bool = False
    engine_io: bool = False
    turn_start_mono: float = 0.0


def log_exchanges(
    trace: DriverTrace,
    *,
    agent_id: str = "agent",
    verbose: int = 0,
    fmt: TraceFormatOptions | None = None,
) -> None:
    if verbose < 1 or not trace.exchanges:
        return
    for ex in trace.exchanges:
        _log_one(agent_id, ex, verbose, fmt=fmt)


def print_exchanges(
    trace: DriverTrace,
    *,
    err: object = sys.stderr,
    agent_id: str = "agent",
    fmt: TraceFormatOptions | None = None,
) -> None:
    """Write formatted exchanges to stderr (ctl --trace)."""
    if not trace.exchanges:
        return
    for ex in trace.exchanges:
        print_exchange(ex, err=err, agent_id=agent_id, fmt=fmt)


def print_exchange(
    ex: ExchangeRecord,
    *,
    err: object = sys.stderr,
    agent_id: str = "agent",
    fmt: TraceFormatOptions | None = None,
) -> None:
    """Write one exchange block (streaming trace)."""
    write = getattr(err, "write", None)
    flush = getattr(err, "flush", None)
    if not callable(write):
        return
    block = format_exchange(agent_id, ex, fmt=fmt)
    write(block)
    if block and not block.endswith("\n"):
        write("\n")
    if callable(flush):
        flush()


def format_exchange(
    agent_id: str,
    ex: ExchangeRecord,
    *,
    fmt: TraceFormatOptions | None = None,
) -> str:
    opts = fmt or TraceFormatOptions()
    lines: list[str] = []
    header = _exchange_header(ex.tag, agent_id)
    if opts.timestamps and ex.ts_wall:
        delta = ""
        if ex.ts_mono and opts.turn_start_mono:
            delta = f" (+{ex.ts_mono - opts.turn_start_mono:.3f}s)"
        lines.append(f"{header}  {ex.ts_wall}{delta}")
    else:
        lines.append(header)
    if ex.detail:
        lines.append(f"  {ex.detail}")
    if opts.engine_io and ex.engine_raw.strip():
        lines.append("  engine:")
        for line in ex.engine_raw.strip().splitlines():
            lines.append(f"    {line}")
    if ex.text.strip():
        for line in ex.text.splitlines():
            lines.append(f"  {line}")
    return "\n".join(lines) + "\n"


def _exchange_header(tag: str, agent_id: str) -> str:
    if tag == "AGENT->LLM":
        return f"\n── AGENT → LLM ({agent_id}) ──"
    if tag == "LLM->AGENT":
        return f"\n── LLM → AGENT ({agent_id}) ──"
    if tag == "AGENT->TOOL":
        return f"\n── AGENT → TOOL ({agent_id}) ──"
    if tag == "TOOL->AGENT":
        return f"\n── TOOL → AGENT ({agent_id}) ──"
    return f"\n── {tag} ──"


def _log_one(
    agent_id: str,
    ex: ExchangeRecord,
    verbose: int,
    *,
    fmt: TraceFormatOptions | None = None,
) -> None:
    block = format_exchange(agent_id, ex, fmt=fmt).strip()
    for line in block.splitlines():
        logger.info("[%s] %s", agent_id, line)


def engine_payload_json(obj: Any) -> str:
    """Compact JSON for EngineIoReturn / InvokeEngineIo trace lines."""
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")
    elif isinstance(obj, dict):
        data = obj
    else:
        return str(obj)
    return json.dumps(data, ensure_ascii=False, indent=2)
