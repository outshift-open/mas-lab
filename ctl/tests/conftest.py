#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pytest configuration for ctl tests."""

import pytest

collect_ignore = ["pending_port"]


@pytest.fixture(autouse=True)
def _clear_library_discovery_caches():
    """Reset the lru_cache-memoized library/catalog discovery helpers.

    See ``runtime/tests/conftest.py`` for the full rationale: these caches
    are keyed by resolved root path, so a test that writes a library dir,
    resolves it, then rewrites the same path must still see the change.
    """
    from mas.library_catalog import clear_catalog_discovery_cache
    from mas.library_roots import clear_library_discovery_cache

    clear_catalog_discovery_cache()
    clear_library_discovery_cache()
    yield
    clear_catalog_discovery_cache()
    clear_library_discovery_cache()
