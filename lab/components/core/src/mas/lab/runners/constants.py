#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stable lab runner identifiers (entry points, analytics, experiment YAML)."""

from __future__ import annotations

DEFAULT_LAB_RUNNER_ID = "native"


def normalize_runner_id(runner_id: str) -> str:
    """Normalize runner id whitespace."""
    return runner_id.strip()
