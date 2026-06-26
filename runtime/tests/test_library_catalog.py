#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for manifest-library filesystem discovery."""

from __future__ import annotations

from mas.apps import get_app, list_apps
from mas.registry import get, list_names


def test_discover_sample_apps() -> None:
    apps = list_apps()
    assert "trip-planner" in apps
    assert "qa-agent" in apps
    root = get_app("trip-planner")
    assert (root / "mas.yaml").is_file()


def test_discover_sample_datasets() -> None:
    names = list_names("dataset")
    assert "trip-planner-benchmark" in names
    assert "trip-planner-benchmark-100" in names
    assert "trip-planner-queries" in names
    path = get("dataset", "trip-planner-benchmark")
    assert path.name == "benchmark.yaml"
    assert "trip-planner" in str(path)
