#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Extra coverage for discover_library_roots anchor handling."""

from __future__ import annotations

from pathlib import Path

from mas.library_roots import discover_library_roots


def test_discover_library_roots_skips_none_anchor(monkeypatch) -> None:
    monkeypatch.delenv("MAS_LIBRARY_PATHS", raising=False)
    # A None anchor must be skipped, not crash.
    roots = discover_library_roots(None)
    assert isinstance(roots, list)


def test_discover_library_roots_finds_anchor_with_library_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MAS_LIBRARY_PATHS", raising=False)
    anchor = tmp_path / "my-lib"
    anchor.mkdir()
    (anchor / "library.yaml").write_text("name: my-lib\n", encoding="utf-8")

    roots = discover_library_roots(anchor)
    assert anchor.resolve() in roots


def test_discover_library_roots_walks_up_to_anchor_parent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MAS_LIBRARY_PATHS", raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "library.yaml").write_text("name: repo\n", encoding="utf-8")
    nested = root / "a" / "b"
    nested.mkdir(parents=True)

    roots = discover_library_roots(nested)
    assert root.resolve() in roots


def test_discover_library_roots_includes_workspace_manifest_libraries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MAS_LIBRARY_PATHS", raising=False)
    ws_root = tmp_path / "ws"
    lib = ws_root / "libx"
    lib.mkdir(parents=True)
    (lib / "library.yaml").write_text("name: libx\n", encoding="utf-8")

    class _FakeWS:
        found = True
        root = ws_root
        manifest_libraries = {"libx": "libx"}

    from mas.runtime.workspace_config import RuntimeWorkspaceConfig

    monkeypatch.setattr(RuntimeWorkspaceConfig, "load", classmethod(lambda cls: _FakeWS()))
    roots = discover_library_roots(tmp_path / "elsewhere")
    assert lib.resolve() in roots


def test_discover_library_roots_workspace_path_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MAS_LIBRARY_PATHS", raising=False)
    ws_root = tmp_path / "ws"
    lib = ws_root / "library-ioc"
    lib.mkdir(parents=True)
    (lib / "library.yaml").write_text("name: mas-library-ioc\n", encoding="utf-8")

    class _FakeWS:
        found = True
        root = ws_root
        # list of paths — name is the directory stem
        manifest_libraries = {"library-ioc": "library-ioc"}

    from mas.runtime.workspace_config import RuntimeWorkspaceConfig

    monkeypatch.setattr(RuntimeWorkspaceConfig, "load", classmethod(lambda cls: _FakeWS()))
    from mas.library_roots import resolve_named_library_root

    assert resolve_named_library_root("library-ioc") == lib.resolve()


def test_workspace_search_path_scans_children(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MAS_LIBRARY_PATHS", raising=False)
    ws_root = tmp_path / "ws"
    lib = ws_root / "library-ioc"
    lib.mkdir(parents=True)
    (lib / "library.yaml").write_text("name: mas-library-ioc\n", encoding="utf-8")

    class _FakeWS:
        found = True
        root = ws_root
        _data = {"manifest_libraries": ["."]}

    from mas.runtime.workspace_config import RuntimeWorkspaceConfig
    from mas.library_roots import resolve_named_library_root

    monkeypatch.setattr(RuntimeWorkspaceConfig, "load", classmethod(lambda cls: _FakeWS()))
    assert resolve_named_library_root("library-ioc") == lib.resolve()
    assert resolve_named_library_root("ws") is None


def test_workspace_config_list_form_uses_directory_stem() -> None:
    from mas.runtime.workspace_config import RuntimeWorkspaceConfig, normalize_manifest_libraries

    assert normalize_manifest_libraries(["./libraries/library-ioc", "lib/"]) == {
        "library-ioc": "./libraries/library-ioc",
        "lib": "lib/",
    }
    cfg = RuntimeWorkspaceConfig({"manifest_libraries": ["library-ioc"]})
    assert cfg.manifest_libraries == {"library-ioc": "library-ioc"}
    legacy = RuntimeWorkspaceConfig({"manifest_libraries": {"eti-apps": "apps"}})
    assert legacy.manifest_libraries == {"eti-apps": "apps"}
