#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Discover benchmark ``metadata.yaml`` files under configured output roots."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from mas.lab import paths as _paths


def iter_metadata_locations(
    *roots: Path,
) -> Iterator[tuple[Path, Path]]:
    """Yield ``(run_dir, metadata_path)`` pairs under each *root*.

    Supports both layouts:

    * **Flat** — ``<root>/metadata.yaml`` (MAS batch with fixed ``-o``)
    * **Nested** — ``<root>/<timestamp>_<id>/metadata.yaml`` (legacy single-agent)
    """
    seen: set[Path] = set()
    seen_pairs: set[tuple[Path, Path]] = set()
    for root in roots:
        if root is None or not root.exists():
            continue
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)

        flat = resolved / "metadata.yaml"
        if flat.is_file():
            pair = (resolved, flat)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                yield resolved, flat

        try:
            children = sorted(resolved.iterdir(), reverse=True)
        except OSError:
            continue

        for child in children:
            if not child.is_dir():
                continue
            nested = child / "metadata.yaml"
            if nested.is_file() and child.resolve() != resolved:
                pair = (child.resolve(), nested.resolve())
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    yield child, nested


def default_search_roots(*, extra: Path | None = None) -> list[Path]:
    """Configured benchmark output roots (labs + runs + optional CLI ``-o``)."""
    return _paths.benchmark_search_roots(extra=extra)
