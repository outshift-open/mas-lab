#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shortcut CLI flags expressed as ``--override`` assignments."""

from __future__ import annotations


def max_tokens_overrides(value: int | None) -> tuple[str, ...]:
    """``--max-tokens N`` is ``--override 'agent:spec.models[*].max_tokens=N'``."""
    if value is None:
        return ()
    return (f"agent:spec.models[*].max_tokens={int(value)}",)
