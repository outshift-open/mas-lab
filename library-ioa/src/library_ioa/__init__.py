#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""IOA Library — MCP client/server bridge for MAS Lab."""

from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Return the directory containing ``library.yaml`` for this manifest library."""
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "library.yaml").is_file():
            return parent
    return here
