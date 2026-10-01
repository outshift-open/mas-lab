#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Placement strategy validation at compose time (before materialize)."""

from __future__ import annotations

from mas.ctl.registry.catalog import (
    UnknownComponentError,
    list_placement_ids,
    validate_placement_id,
)

OSS_SUPPORTED_STRATEGIES = frozenset(list_placement_ids())


def _library_next_installed() -> bool:
    try:
        import mas.library.next  # noqa: F401

        return True
    except ImportError:
        return False


def validate_placement_strategy(strategy: str) -> None:
    """Reject unsupported placement strategies with a clear error at compose time."""
    try:
        validate_placement_id(strategy)
    except UnknownComponentError as exc:
        message = str(exc.args[0]) if exc.args else str(exc)
        if message.startswith("unknown placement id"):
            raise RuntimeError(
                f"unknown placement strategy {strategy!r}; "
                f"expected one of {sorted(OSS_SUPPORTED_STRATEGIES)}"
            ) from exc
        raise RuntimeError(
            f"placement strategy {strategy!r} is not available in mas-lab OSS "
            f"(only {sorted(OSS_SUPPORTED_STRATEGIES)} is supported)."
        ) from exc
