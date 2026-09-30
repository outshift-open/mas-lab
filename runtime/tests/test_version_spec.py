#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.version_spec import app_satisfies, parse_app_dependency, version_satisfies


def test_parse_app_dependency_forms() -> None:
    dep = parse_app_dependency("trip-planner@>=v1,<v3")
    assert dep is not None
    assert dep.name == "trip-planner"
    assert dep.spec == ">=v1,<v3"
    assert dep.library is None
    qualified = parse_app_dependency("example-library:trip-planner@^v1")
    assert qualified is not None
    assert qualified.library == "example-library"
    assert qualified.spec == "^v1"
    bare = parse_app_dependency("trip-planner")
    assert bare is not None
    assert bare.spec is None
    structured = parse_app_dependency({"name": "trip-planner", "version": ">=v1,<v3"})
    assert structured is not None
    assert structured.name == "trip-planner"
    assert structured.spec == ">=v1,<v3"


def test_version_satisfies_exact_and_range() -> None:
    assert version_satisfies("v1", "v1")
    assert version_satisfies("v1", "==v1")
    assert not version_satisfies("v2", "v1")
    assert version_satisfies("v1", ">=v1,<v3")
    assert version_satisfies("v2", ">=v1,<v3")
    assert not version_satisfies("v3", ">=v1,<v3")
    assert version_satisfies("v1.1", "^v1")
    assert not version_satisfies("v2", "^v1")


def test_app_satisfies_dataset_dependency() -> None:
    assert app_satisfies("trip-planner@v1", "trip-planner@>=v1,<v3")
    assert app_satisfies("example-library:trip-planner@v2", "trip-planner@>=v1,<v3")
    assert not app_satisfies("trip-planner@v2", "trip-planner@v1")
    assert not app_satisfies("coding-agent@v1", "trip-planner@>=v1,<v3")
    assert app_satisfies("trip-planner@v1", "trip-planner")
    assert app_satisfies("trip-planner@v9", None)
