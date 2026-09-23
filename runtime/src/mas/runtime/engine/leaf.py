#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unwrap infra pipeline facades to the leaf engine."""

from __future__ import annotations

from typing import Any

from mas.runtime.contracts.tool_semantics import existing_attr


def leaf_engine(engine: Any) -> Any:
    """Return the innermost engine that handles LLM/tool IO.

    Reads ``.inner`` without ``__getattr__`` so a spec-less ``MagicMock``
    cannot auto-create an unbounded wrapper chain.
    """
    seen: set[int] = set()
    current = engine
    for _ in range(8):
        if current is None or id(current) in seen:
            return current
        seen.add(id(current))
        inner = existing_attr(current, "inner")
        if inner is None or inner is current:
            return current
        current = inner
    return current
