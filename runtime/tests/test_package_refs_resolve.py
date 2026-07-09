#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for the manifest-library-relative path resolver added with the
registry refactor (``_resolve_in_library`` / ``resolve_path_ref``)."""

from __future__ import annotations

from pathlib import Path

import pytest

import mas.runtime.package_refs as package_refs
from mas.runtime.package_refs import _resolve_in_library, resolve_path_ref


def test_resolve_in_library_explicit_yaml(tmp_path: Path) -> None:
    target = tmp_path / "pipelines" / "native-to-otel-json.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")

    assert _resolve_in_library(tmp_path, "pipelines/native-to-otel-json.yaml") == target


def test_resolve_in_library_extension_implied(tmp_path: Path) -> None:
    target = tmp_path / "pipelines" / "native-to-otel-json.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")

    # `.yaml` omitted -> resolved via the extension-candidate branch.
    assert _resolve_in_library(tmp_path, "pipelines/native-to-otel-json") == target


def test_resolve_in_library_pipelines_and_extension_implied(tmp_path: Path) -> None:
    target = tmp_path / "pipelines" / "native-to-otel-json.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")

    # Neither `pipelines/` nor `.yaml` given -> resolved via the combined branch.
    assert _resolve_in_library(tmp_path, "native-to-otel-json") == target


def test_resolve_in_library_yml_extension(tmp_path: Path) -> None:
    target = tmp_path / "flow.yml"
    target.write_text("x", encoding="utf-8")
    assert _resolve_in_library(tmp_path, "flow") == target


def test_resolve_in_library_leading_slash_stripped(tmp_path: Path) -> None:
    target = tmp_path / "flow.yaml"
    target.write_text("x", encoding="utf-8")
    assert _resolve_in_library(tmp_path, "/flow.yaml") == target


def test_resolve_in_library_missing_returns_literal(tmp_path: Path) -> None:
    # Nothing exists -> literal lib_root / rel is returned (caller raises).
    assert _resolve_in_library(tmp_path, "nope") == tmp_path / "nope"


def test_resolve_path_ref_uses_library_scheme(tmp_path: Path, monkeypatch) -> None:
    lib_root = tmp_path / "lib"
    target = lib_root / "pipelines" / "flow.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        package_refs, "_manifest_library_root", lambda scheme: lib_root if scheme == "telemetry" else None
    )

    assert resolve_path_ref("telemetry:flow", tmp_path) == target


def test_resolve_path_ref_relative_path(tmp_path: Path) -> None:
    out = resolve_path_ref("sub/thing.yaml", tmp_path)
    assert out == (tmp_path / "sub" / "thing.yaml").resolve()


def test_resolve_path_ref_absolute_path(tmp_path: Path) -> None:
    abs_path = (tmp_path / "abs.yaml").resolve()
    assert resolve_path_ref(str(abs_path), tmp_path) == abs_path


def test_resolve_path_ref_unknown_scheme_falls_through_to_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(package_refs, "_manifest_library_root", lambda scheme: None)
    # Unknown scheme -> not treated as a library ref, resolved as a plain path.
    out = resolve_path_ref("unknown:thing", tmp_path)
    assert out == (tmp_path / "unknown:thing").resolve()


def test_resolve_path_ref_pkg_without_resource_path_raises() -> None:
    with pytest.raises(ValueError):
        resolve_path_ref("pkg://somepackage", Path.cwd())
