#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve manifest schema files from installed package dependencies."""
from __future__ import annotations

from pathlib import Path


def runtime_schema_dir() -> Path:
    """YAML schemas shipped with mas-runtime / docs/schemas/runtime."""
    from mas.ctl.validate.schemas import _SCHEMA_ROOT

    return _SCHEMA_ROOT / "runtime"


def _repo_root() -> Path:
    """Repository root (contains docs/schemas/)."""
    return Path(__file__).resolve().parents[7]


def lab_schema_dir() -> Path:
    """YAML/JSON schemas for mas-lab manifests (experiment, pipeline, dataset, lab-config)."""
    return _repo_root() / "docs" / "schemas" / "lab"


def lab_artefact_schema_dir() -> Path:
    """JSON schemas for per-run benchmark artefacts (metrics.json, run_info.json)."""
    return lab_schema_dir() / "artefacts"


def bench_schema_dir() -> Path:
    """Alias for :func:`lab_schema_dir` — single canonical schema tree under docs/."""
    return lab_schema_dir()


def editor_schema_dir() -> Path:
    """JSON editor schemas for mas-lab-ui form builders (subset of runtime fields)."""
    return Path(__file__).resolve().parent / "ui"
