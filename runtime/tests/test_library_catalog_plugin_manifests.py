#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for plugin-manifest discovery in mas.library_catalog.

library.yaml doubles as the plugin manifest: when it declares
types:/plugins: directly, it is registered the same way as a split-out
*.plugins.yaml file. See runtime/docs/plugin-registry-manifests.md.

`plugins:` is always a list of inline plugin declarations. The split-file
catalog convention (name -> relative path to another manifest) uses a
different key, `plugin_manifests:`, specifically so discovery never has to
guess which convention a `plugins:` key belongs to.
"""

from __future__ import annotations

import mas.library_catalog as library_catalog
from mas.library_catalog import (
    _declares_plugins,
    discover_plugin_manifests,
)


def test_declares_plugins_checks_key_presence_not_value_shape() -> None:
    assert _declares_plugins({"types": ["step"], "plugins": [{"type": "step"}]}) is True
    # A `types:` declaration alone is also enough.
    assert _declares_plugins({"types": ["step"]}) is True
    # `plugin_manifests:` (the split-file catalog) is a distinct key -- its
    # presence never makes this library.yaml itself a plugin manifest.
    assert _declares_plugins({"plugin_manifests": {"steps": "plugins/steps.plugins.yaml"}}) is False
    # Plain library metadata, no plugin content at all.
    assert _declares_plugins({"name": "mas-library-x", "version": "0.1.0"}) is False
    # Empty plugins list should not count (nothing to register).
    assert _declares_plugins({"plugins": []}) is False


def test_discover_plugin_manifests_finds_inline_library_yaml(tmp_path, monkeypatch) -> None:
    root = tmp_path / "library-x"
    root.mkdir()
    (root / "library.yaml").write_text(
        """apiVersion: mas/v1
kind: Library
name: mas-library-x
version: "0.1.0"
types:
  - widget
plugins:
  - type: widget
    name: gizmo
    module: pathlib
    class: Path
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(library_catalog, "discover_library_roots", lambda: [root])

    manifests = discover_plugin_manifests()
    assert manifests == [(root / "library.yaml").resolve()]


def test_discover_plugin_manifests_scan_fallback_still_works(tmp_path, monkeypatch) -> None:
    """A library may still split plugins into plugins/*.plugins.yaml if it wants to."""
    root = tmp_path / "library-y"
    root.mkdir()
    (root / "library.yaml").write_text(
        "apiVersion: mas/v1\nkind: Library\nname: mas-library-y\nversion: \"0.1.0\"\n", encoding="utf-8"
    )
    plugins_dir = root / "plugins"
    plugins_dir.mkdir()
    split_manifest = plugins_dir / "widgets.plugins.yaml"
    split_manifest.write_text(
        "types: [widget]\nplugins:\n  - type: widget\n    name: gizmo\n    module: pathlib\n    class: Path\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(library_catalog, "discover_library_roots", lambda: [root])

    manifests = discover_plugin_manifests()
    # library.yaml itself has no inline plugin content, so only the split file is found.
    assert manifests == [split_manifest.resolve()]


def test_discover_plugin_manifests_from_catalog_resolves_relative_paths(tmp_path) -> None:
    """The `plugin_manifests:` name -> relative-path catalog convention (an
    alternative to the inline shape, for libraries that want an explicit
    index instead of a directory scan)."""
    root = tmp_path / "library-z"
    root.mkdir()
    plugins_dir = root / "plugins"
    plugins_dir.mkdir()
    catalog_target = plugins_dir / "extra.plugins.yaml"
    catalog_target.write_text(
        "types: [tool]\nplugins:\n  - type: tool\n    name: helper\n    module: pathlib\n    class: Path\n",
        encoding="utf-8",
    )

    from mas.library_catalog import _discover_plugin_manifests_from_catalog

    catalog_manifest = {"plugin_manifests": {"extra": "plugins/extra.plugins.yaml"}}
    assert _discover_plugin_manifests_from_catalog(root, catalog_manifest) == [catalog_target.resolve()]


def test_discover_plugin_manifests_dedupes_and_combines_inline_plus_scan(tmp_path, monkeypatch) -> None:
    root = tmp_path / "library-w"
    root.mkdir()
    plugins_dir = root / "plugins"
    plugins_dir.mkdir()
    scan_target = plugins_dir / "scanned.plugins.yaml"
    scan_target.write_text(
        "types: [tool]\nplugins:\n  - type: tool\n    name: helper2\n    module: pathlib\n    class: Path\n",
        encoding="utf-8",
    )
    (root / "library.yaml").write_text(
        """apiVersion: mas/v1
kind: Library
name: mas-library-w
version: "0.1.0"
types:
  - widget
plugins:
  - type: widget
    name: gizmo
    module: pathlib
    class: Path
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(library_catalog, "discover_library_roots", lambda: [root])

    manifests = discover_plugin_manifests()
    # inline library.yaml (its own types:/plugins:) *and* the scan-discovered
    # split file are both registered -- additive, not either/or.
    assert (root / "library.yaml").resolve() in manifests
    assert scan_target.resolve() in manifests
    assert len(manifests) == len(set(manifests)), "no duplicate paths"
