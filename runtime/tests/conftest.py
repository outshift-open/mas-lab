#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pytest configuration for runtime tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def require_samples_library() -> None:
    """Skip when the ``samples`` manifest library entry point is not installed."""
    from mas.runtime.package_refs import resolve_library_scheme_root

    if resolve_library_scheme_root("samples") is None:
        pytest.skip("mas-library-samples not installed")
