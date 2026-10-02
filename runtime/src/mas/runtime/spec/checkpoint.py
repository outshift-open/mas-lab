#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Validated checkpoint cadence and retention policy from ``spec.checkpoint``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CheckpointSpecError(ValueError):
    """Checkpoint policy is malformed or uses an unsupported option."""


@dataclass(frozen=True)
class CheckpointPolicy:
    """Checkpointing behavior selected by one agent manifest."""

    mode: str = "none"
    triggers: tuple[str, ...] = ()
    every_n_turns: int | None = None
    retention_mode: str = "all"
    retention_n: int = 5
    portability: str = "self_contained"
    auto_resume_latest: bool = False


_MODES = {"none", "in_memory", "on_event", "every_turn"}
_TRIGGERS = {"after_llm_call", "after_tool_call", "before_destructive_tool", "every_n_turns"}
_RETENTION_MODES = {"all", "single", "last_n"}


def parse_checkpoint_policy(raw: Any) -> CheckpointPolicy:
    """Parse strict ``spec.checkpoint`` fields with behavior-preserving defaults."""
    if raw is None:
        return CheckpointPolicy()
    if not isinstance(raw, dict):
        raise CheckpointSpecError("spec.checkpoint must be an object")
    unknown = set(raw) - {
        "mode",
        "triggers",
        "every_n_turns",
        "retention",
        "portability",
        "auto_resume_latest",
    }
    if unknown:
        raise CheckpointSpecError(f"spec.checkpoint: unknown field {sorted(unknown)[0]!r}")

    mode = raw.get("mode", "none")
    if mode not in _MODES:
        raise CheckpointSpecError(f"spec.checkpoint.mode must be one of {sorted(_MODES)}")
    triggers_raw = raw.get("triggers", [])
    if not isinstance(triggers_raw, list) or any(
        not isinstance(trigger, str) or trigger not in _TRIGGERS for trigger in triggers_raw
    ):
        raise CheckpointSpecError(f"spec.checkpoint.triggers must contain only {sorted(_TRIGGERS)}")
    triggers = tuple(dict.fromkeys(triggers_raw))

    every_n_turns = raw.get("every_n_turns")
    if every_n_turns is not None and (
        not isinstance(every_n_turns, int)
        or isinstance(every_n_turns, bool)
        or every_n_turns < 1
    ):
        raise CheckpointSpecError("spec.checkpoint.every_n_turns must be an integer >= 1")

    retention = raw.get("retention", {})
    if not isinstance(retention, dict) or set(retention) - {"mode", "n"}:
        raise CheckpointSpecError("spec.checkpoint.retention must contain only mode and n")
    retention_mode = retention.get("mode", "all")
    if retention_mode not in _RETENTION_MODES:
        raise CheckpointSpecError(f"spec.checkpoint.retention.mode must be one of {sorted(_RETENTION_MODES)}")
    retention_n = retention.get("n", 5)
    if not isinstance(retention_n, int) or isinstance(retention_n, bool) or retention_n < 1:
        raise CheckpointSpecError("spec.checkpoint.retention.n must be an integer >= 1")

    portability = raw.get("portability", "self_contained")
    if portability not in {"self_contained", "reference"}:
        raise CheckpointSpecError("spec.checkpoint.portability must be self_contained or reference")
    auto_resume_latest = raw.get("auto_resume_latest", False)
    if not isinstance(auto_resume_latest, bool):
        raise CheckpointSpecError("spec.checkpoint.auto_resume_latest must be a boolean")
    if auto_resume_latest and mode == "in_memory":
        raise CheckpointSpecError("spec.checkpoint.auto_resume_latest requires a persistent checkpoint mode")

    return CheckpointPolicy(
        mode=mode,
        triggers=triggers,
        every_n_turns=every_n_turns,
        retention_mode=retention_mode,
        retention_n=retention_n,
        portability=portability,
        auto_resume_latest=auto_resume_latest,
    )