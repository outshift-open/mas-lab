#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unwrap infra pipeline facades to the leaf engine."""

from __future__ import annotations

from typing import Any


def leaf_engine(engine: Any) -> Any:
    """Return the innermost engine that handles LLM/tool IO."""
    seen: set[int] = set()
    current = engine
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        inner = getattr(current, "inner", None)
        if inner is None:
            return current
        current = inner
    return current
