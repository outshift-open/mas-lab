#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Placement strategy validation at compose time (before materialize)."""

from __future__ import annotations

OSS_SUPPORTED_STRATEGIES = frozenset({"local-inproc"})

_LIBRARY_NEXT_STRATEGIES = frozenset({"local-multiprocess", "docker", "kubernetes"})


def _library_next_installed() -> bool:
    try:
        import mas.library.next  # noqa: F401

        return True
    except ImportError:
        return False


def validate_placement_strategy(strategy: str) -> None:
    """Reject unsupported placement strategies with a clear error at compose time."""
    if strategy in OSS_SUPPORTED_STRATEGIES:
        return

    if strategy in _LIBRARY_NEXT_STRATEGIES:
        if not _library_next_installed():
            raise RuntimeError(
                f"placement strategy {strategy!r} is not available in mas-lab OSS "
                f"(only {sorted(OSS_SUPPORTED_STRATEGIES)} is supported)."
            )
        return

    raise RuntimeError(
        f"unknown placement strategy {strategy!r}; "
        f"expected one of {sorted(OSS_SUPPORTED_STRATEGIES | _LIBRARY_NEXT_STRATEGIES)}"
    )
