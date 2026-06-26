#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Flavours resolve only from mas-library-standard."""

from __future__ import annotations

import pytest

from mas.lab.flavour.resolve import bundled_flavour_path, resolve_flavour_path


@pytest.mark.parametrize("name", ["local", "lib:local", "local-benchmark", "mock"])
def test_bundled_flavours_exist(name: str) -> None:
    path = resolve_flavour_path(name)
    assert path.is_file()
    assert "library" in str(path) and "standard" in str(path)


def test_unknown_flavour_raises() -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        resolve_flavour_path("does-not-exist")


def test_bundled_flavour_path_local() -> None:
    assert bundled_flavour_path("local") is not None
