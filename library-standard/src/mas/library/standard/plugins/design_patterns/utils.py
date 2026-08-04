#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared utility functions for deterministic design patterns."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.egress_gate import schedule_tool_egress
from mas.runtime.kernel.parallel_tools import schedule_parallel_tools_egress
from mas.runtime.kernel.state import QProduct, RunLedger
from mas.runtime.schema.egress import EgressSymbol
from mas.runtime.schema.ingress import ToolCallSpec

if TYPE_CHECKING:
    from .base import _DeterministicBase


def dispatch_single(
    pattern: _DeterministicBase,
    q: QProduct,
    run: RunLedger,
    config: KernelConfig,
    task: str,
    participant: str,
) -> list[EgressSymbol]:
    """Dispatch task to a single agent."""
    q.pending_tool_name = pattern._delegate_tool_name(participant)
    q.pending_tool_args = {"task": task}
    return schedule_tool_egress(q, run, config)


def dispatch_parallel(
    pattern: _DeterministicBase,
    q: QProduct,
    run: RunLedger,
    config: KernelConfig,
    task: str,
    participants: list[str],
) -> list[EgressSymbol]:
    """Dispatch task to all participants in parallel."""
    specs = [
        ToolCallSpec(tool_name=pattern._delegate_tool_name(p), tool_arguments={"task": task})
        for p in participants
    ]
    return schedule_parallel_tools_egress(q, run, config, specs)


def majority_vote(answers: list[str]) -> str:
    """Return the most common answer; falls back to a neutral string if empty."""
    if not answers:
        return "Deterministic run complete (no outputs)."
    winner, _ = Counter(answers).most_common(1)[0]
    return winner
