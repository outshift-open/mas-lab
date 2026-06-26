#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from mas.apps import get_app
from mas.lab.lab.config import MASSpec
from mas.runtime.package_refs import resolve_path_ref


def test_trip_planner_manifest_via_app_registry() -> None:
    path = get_app("trip-planner") / "mas.yaml"
    assert path.is_file()
    assert path.name == "mas.yaml"
    assert path.parent.name == "trip-planner"


def test_resolve_path_ref_manifest_library_scheme() -> None:
    path = resolve_path_ref("samples:apps/trip-planner/mas.yaml", Path.cwd())
    assert path.is_file()
    assert path.name == "mas.yaml"
    assert "trip-planner" in str(path)
    assert "trip-planner-linear" not in str(path)


def test_masspec_from_dict_supports_app_locator() -> None:
    spec = MASSpec.from_dict(
        {"app": "trip-planner", "base_scenario": "baseline"},
        Path.cwd(),
    )
    assert spec.manifest is not None
    assert spec.manifest.is_file()
    assert spec.manifest.parent.name == "trip-planner"
