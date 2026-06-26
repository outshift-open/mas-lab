#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas.runtime.spec.source."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mas.runtime.spec.source import (
    load_yaml_file,
    resolve_manifest_source,
    resolve_ref_with_search,
    resolve_yaml_path,
    resolve_yaml_source,
)


def test_resolve_yaml_path_relative(tmp_path: Path) -> None:
    f = tmp_path / "agent.yaml"
    f.write_text("kind: Agent\n", encoding="utf-8")
    assert resolve_yaml_path("agent.yaml", tmp_path) == f.resolve()


def test_resolve_yaml_source_inline_first(tmp_path: Path) -> None:
    inline = {"steps": [{"name": "a"}]}
    out = resolve_yaml_source(inline=inline, anchor=tmp_path)
    assert out == inline


def test_resolve_yaml_source_ref(tmp_path: Path) -> None:
    f = tmp_path / "pipe.yaml"
    yaml.safe_dump({"steps": [{"name": "x"}]}, f.open("w"))
    out = resolve_yaml_source(ref="pipe.yaml", anchor=tmp_path)
    assert out["steps"][0]["name"] == "x"


def test_resolve_manifest_source_str_path(tmp_path: Path) -> None:
    f = tmp_path / "agent.yaml"
    f.write_text("kind: Agent\n", encoding="utf-8")
    data = resolve_manifest_source(str(f), anchor=tmp_path)
    assert data["kind"] == "Agent"


def test_resolve_ref_with_search(tmp_path: Path) -> None:
    sub = tmp_path / "infra"
    sub.mkdir()
    f = sub / "local.yaml"
    f.write_text("kind: Infra\n", encoding="utf-8")
    path = resolve_ref_with_search("local", tmp_path, search_dirs=[sub])
    assert path == f.resolve()


def test_resolve_yaml_path_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_yaml_path("missing.yaml", tmp_path)


def test_load_yaml_file(tmp_path: Path) -> None:
    f = tmp_path / "x.yaml"
    f.write_text("a: 1\n", encoding="utf-8")
    assert load_yaml_file(f) == {"a": 1}
