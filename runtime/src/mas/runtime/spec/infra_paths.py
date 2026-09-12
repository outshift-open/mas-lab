#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Experiment infra bundle paths — shared by bench prep and lab pipeline steps."""

from __future__ import annotations

from pathlib import Path


def _infra_filename(name: str) -> str:
    stripped = (name or "").strip()
    if not stripped:
        raise ValueError("infra name must be non-empty")
    return stripped if stripped.endswith((".yaml", ".yml")) else f"{stripped}.yaml"


def experiment_infra_bundle_path(experiment_dir: Path, name: str) -> Path | None:
    """Return ``<experiment_dir>/infra/<name>.yaml`` when that file exists."""
    path = experiment_dir / "infra" / _infra_filename(name)
    return path if path.is_file() else None


def resolve_infra_bundle(
    experiment_dir: Path,
    name: str,
    *,
    search_workspace: bool = False,
) -> Path | None:
    """Locate an infra bundle YAML for a lab/bench experiment.

    Resolution order:
    1. ``<experiment_dir>/infra/<name>.yaml``
    2. When ``search_workspace`` is true, walk parents for ``infra/<name>.yaml``
       (stops at a directory that has both ``pyproject.toml`` and ``infra/``).
    """
    local = experiment_infra_bundle_path(experiment_dir, name)
    if local is not None:
        return local
    if not search_workspace:
        return None

    filename = _infra_filename(name)
    for parent in [experiment_dir, *experiment_dir.parents]:
        candidate = parent / "infra" / filename
        if candidate.is_file():
            return candidate
        if (parent / "pyproject.toml").is_file() and (parent / "infra").is_dir():
            break
    return None
