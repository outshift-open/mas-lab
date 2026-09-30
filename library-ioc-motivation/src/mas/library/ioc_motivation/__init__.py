#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-library-ioc-motivation — manifest library root for the IoC reproduction experiments."""

from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    """Return the directory containing ``library.yaml`` and the library content.

    Installed wheels bundle the content next to this module.  Editable checkouts
    keep a flat layout at the project root; walk up to find it.
    """
    here = Path(__file__).resolve().parent
    if (here / "library.yaml").is_file():
        return here

    for parent in here.parents:
        if (parent / "library.yaml").is_file() and (parent / "apps").is_dir():
            return parent

    return here
