#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.version_spec import app_satisfies, parse_app_dependency, version_satisfies


def test_parse_app_dependency_forms() -> None:
    dep = parse_app_dependency("sre-triage@>=v1,<v3")
    assert dep is not None
    assert dep.name == "sre-triage"
    assert dep.spec == ">=v1,<v3"
    assert dep.library is None
    qualified = parse_app_dependency("library-ioc:sre-triage@^v1")
    assert qualified is not None
    assert qualified.library == "library-ioc"
    assert qualified.spec == "^v1"
    bare = parse_app_dependency("sre-triage")
    assert bare is not None
    assert bare.spec is None
    structured = parse_app_dependency({"name": "sre-triage", "version": ">=v1,<v3"})
    assert structured is not None
    assert structured.name == "sre-triage"
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
    assert app_satisfies("sre-triage@v1", "sre-triage@>=v1,<v3")
    assert app_satisfies("library-ioc:sre-triage@v2", "sre-triage@>=v1,<v3")
    assert not app_satisfies("sre-triage@v2", "sre-triage@v1")
    assert not app_satisfies("coding-agent@v1", "sre-triage@>=v1,<v3")
    assert app_satisfies("sre-triage@v1", "sre-triage")
    assert app_satisfies("sre-triage@v9", None)
