#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Infra-manifest (Neo4j target) tests for library-kg."""

from __future__ import annotations

from pathlib import Path

import pytest

from mas.library.kg.infra import Neo4jTarget, neo4j_target

_MANIFEST = {
    "apiVersion": "mas/v1",
    "kind": "Infra",
    "metadata": {"name": "local-neo4j"},
    "spec": {
        "targets": [
            {
                "kind": "Neo4j",
                "uri": "bolt://db:7687",
                "database": "kg",
                "username": "u",
                "password_env": "PW",
            },
            {"kind": "OtelCollector", "endpoint": "http://localhost:4318"},
        ]
    },
}


def test_resolve_from_dict():
    t = neo4j_target(_MANIFEST)
    assert isinstance(t, Neo4jTarget)
    assert t.resolved_uri() == "bolt://db:7687"
    assert t.resolved_database() == "kg"
    assert t.resolved_username() == "u"


def test_password_from_env_never_manifest(monkeypatch):
    t = neo4j_target(_MANIFEST)
    # Only the env-var NAME is stored — never a literal `password:` value.
    assert all("password" not in tgt for tgt in _MANIFEST["spec"]["targets"])
    monkeypatch.setenv("PW", "secret")
    assert t.password() == "secret"


def test_overrides_win():
    t = Neo4jTarget(uri="bolt://manifest:7687")
    assert t.resolved_uri("bolt://override:7687") == "bolt://override:7687"


def test_shipped_yaml_manifest():
    manifest = Path(__file__).resolve().parents[1] / "infra" / "local-neo4j.yaml"
    assert neo4j_target(manifest).resolved_uri() == "bolt://localhost:7687"


def test_env_is_shortcut_for_neo4j_manifest(monkeypatch):
    from mas.library.kg.infra import resolve_neo4j

    monkeypatch.setenv("NEO4J_URI", "bolt://from-env:7687")
    t = resolve_neo4j()
    assert t.uri == "bolt://from-env:7687"


def test_missing_target_raises():
    with pytest.raises(ValueError):
        neo4j_target({"kind": "Infra", "spec": {"targets": [{"kind": "OtelCollector"}]}})
