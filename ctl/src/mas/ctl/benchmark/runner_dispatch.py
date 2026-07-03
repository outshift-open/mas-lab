#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Bench runner routing helpers — manifest kind detection for MasBenchRunner."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def is_mas_manifest_kind(config: dict[str, Any], spec_path: Path) -> bool:
    """True when *config* / *spec_path* denote a MAS (not a standalone agent) manifest."""
    kind = str(config.get("kind", "")).lower()
    if kind == "agent":
        return False
    if kind in ("mas", "app", "workflow"):
        return True
    if spec_path.name in ("mas.yaml", "mas.yml") or spec_path.name.startswith("mas."):
        return True
    return (spec_path.parent / "mas.yaml").is_file()


def mas_manifest_path(config: dict[str, Any], spec_path: Path) -> Path | None:
    """Return the MAS manifest path when *config* is a MAS; otherwise ``None``."""
    if not is_mas_manifest_kind(config, spec_path):
        return None
    kind = str(config.get("kind", "")).lower()
    if kind in ("mas", "app", "workflow"):
        return spec_path
    if spec_path.name in ("mas.yaml", "mas.yml") or spec_path.name.startswith("mas."):
        return spec_path
    sibling = spec_path.parent / "mas.yaml"
    return sibling if sibling.is_file() else None
