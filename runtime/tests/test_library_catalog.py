#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for manifest-library filesystem discovery."""

from __future__ import annotations

from mas.apps import get_app, list_apps
from mas.registry import get, list_names, list_objects


def test_discover_sample_apps() -> None:
    apps = list_apps()
    assert "trip-planner" in apps
    trip_root = get_app("trip-planner")
    assert (trip_root / "mas.yaml").is_file()


def test_discover_sample_datasets() -> None:
    names = list_names("dataset")
    assert "trip-planner-benchmark" in names
    assert "trip-planner-benchmark-100" in names
    assert "trip-planner-queries" in names
    path = get("dataset", "trip-planner-benchmark")
    assert path.name == "benchmark.yaml"
    assert "trip-planner" in str(path)


def test_list_objects_matches_list_names_and_get() -> None:
    """list_objects() must agree with the per-name get()/list_names() API."""
    objects = list_objects("dataset")
    names = list_names("dataset")
    assert set(objects) == set(names)
    for name in names:
        assert objects[name] == get("dataset", name)


def test_list_objects_performs_a_single_discovery_pass(monkeypatch) -> None:
    """Regression guard for the N+1 rescan bug: list_objects() must call
    _discover() exactly once, not once per object (as a get() loop would)."""
    import mas.registry as registry_mod

    calls = {"n": 0}
    real_discover = registry_mod._discover

    def counting_discover(kind: str):
        calls["n"] += 1
        return real_discover(kind)

    monkeypatch.setattr(registry_mod, "_discover", counting_discover)
    objects = registry_mod.list_objects("dataset")
    assert len(objects) > 1, "fixture must expose more than one dataset for this guard to be meaningful"
    assert calls["n"] == 1
