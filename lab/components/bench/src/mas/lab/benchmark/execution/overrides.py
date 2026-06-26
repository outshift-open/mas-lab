#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""CLI step override parsing for benchmark pipelines."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def parse_step_overrides(raw: Optional[list]) -> dict:
    """Parse ``--set STEP.KEY=VALUE`` strings into ``{step_type: {key: value}}``."""
    result: dict = {}
    for item in raw or []:
        if "." not in item or "=" not in item:
            logger.warning("--set: ignoring malformed override %r (expected STEP.KEY=VALUE)", item)
            continue
        step_key, value_str = item.split("=", 1)
        parts = step_key.split(".", 1)
        if len(parts) != 2:
            logger.warning("--set: ignoring malformed override %r (expected STEP.KEY=VALUE)", item)
            continue
        step_type, key = parts
        low = value_str.lower()
        if low == "true":
            value: Any = True
        elif low == "false":
            value = False
        else:
            try:
                value = int(value_str)
            except ValueError:
                try:
                    value = float(value_str)
                except ValueError:
                    value = value_str
        result.setdefault(step_type, {})[key] = value
    return result


def apply_step_overrides(step_config: dict, step_type: str, overrides: dict) -> dict:
    """Merge CLI overrides for *step_type* into a copy of *step_config*."""
    if not overrides or step_type not in overrides:
        return step_config
    merged = dict(step_config)
    merged.update(overrides[step_type])
    return merged
