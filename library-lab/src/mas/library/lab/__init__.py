#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.library.lab package."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def package_root() -> Path:
    """Return the directory containing ``library.yaml`` for this manifest library."""
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "library.yaml").is_file():
            return parent
    return here

try:
    __version__ = version("mas-library-lab")
except PackageNotFoundError:
    __version__ = "0.1.0"

from mas.library.lab.plots import execution_chain_graph

__all__ = ["execution_chain_graph"]
