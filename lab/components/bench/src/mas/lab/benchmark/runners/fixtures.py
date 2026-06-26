#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Run-input tool fixture sidecars for mock tool providers."""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def write_tool_fixtures_sidecar(spec_path: Path, tool_fixtures: Any) -> None:
    """Write envelope ``tool_fixtures`` to ``<use-case>/artifacts/scene.yaml``."""
    if tool_fixtures is None:
        return

    sidecar_dir = spec_path.parent / "artifacts"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = sidecar_dir / "scene.yaml"
    payload = tool_fixtures if isinstance(tool_fixtures, (dict, list)) else {"data": tool_fixtures}
    with open(sidecar_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, default_flow_style=False, allow_unicode=True)
    logger.debug("Wrote tool fixtures sidecar: %s", sidecar_path)
