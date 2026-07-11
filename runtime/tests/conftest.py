#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pytest configuration for runtime tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_workspace_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear ``MAS_WORKSPACE_ROOT`` so ``RuntimeWorkspaceConfig.load(start=...)``
    resolves the ``start`` a test passed instead of silently deferring to
    whatever the outer test session's ``conftest.py`` exported for its own
    sample-workspace isolation (``find_workspace_file`` checks the env var
    before ``start`` — see ``mas.runtime.workspace_config``). Without this,
    tests here pass in isolation but fail when the full suite runs them after
    ``tests/conftest.py`` has set the variable for the process's lifetime.
    """
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)


@pytest.fixture
def require_samples_library() -> None:
    """Skip when the ``samples`` manifest library entry point is not installed."""
    from mas.runtime.package_refs import resolve_library_scheme_root

    if resolve_library_scheme_root("samples") is None:
        pytest.skip("mas-library-samples not installed")
