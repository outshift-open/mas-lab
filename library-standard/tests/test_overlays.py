#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""library-standard overlays: index, shape, merge, packaged URI."""

from __future__ import annotations

from pathlib import Path

import yaml

OVERLAYS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "mas"
    / "library"
    / "standard"
    / "overlays"
)
INDEX = OVERLAYS / "README.md"


def _overlay_yaml_files() -> list[Path]:
    return sorted(p for p in OVERLAYS.glob("*.yaml") if p.is_file())


def test_index_lists_every_overlay_file() -> None:
    readme = INDEX.read_text(encoding="utf-8")
    files = _overlay_yaml_files()
    assert files, "expected at least one overlay yaml"
    for path in files:
        assert path.name in readme, f"{path.name} missing from overlays/README.md"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        name = (doc.get("metadata") or {}).get("name")
        assert name, f"{path.name} has no metadata.name"
        assert str(name) in readme, f"{name} missing from overlays/README.md"


def test_every_overlay_is_mas_v1_agent_overlay() -> None:
    for path in _overlay_yaml_files():
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert doc["apiVersion"] == "mas/v1"
        assert doc["kind"] == "Overlay"
        assert (doc.get("spec") or {}).get("target", {}).get("kind") == "Agent"
        assert (doc.get("spec") or {}).get("patch")


def test_with_hardened_appends_gov_no_undeclared_tool() -> None:
    doc = yaml.safe_load((OVERLAYS / "with-hardened.yaml").read_text(encoding="utf-8"))
    add = doc["spec"]["patch"]["governance"]["$op"]["add"]
    assert "gov_no_undeclared_tool" in add


def test_observability_native_sets_events_jsonl() -> None:
    doc = yaml.safe_load((OVERLAYS / "observability-native.yaml").read_text(encoding="utf-8"))
    obs = doc["spec"]["patch"]["observability"]
    native = next(item for item in obs if isinstance(item, dict) and "native" in item)
    assert native["native"]["path"] == "traces/events.jsonl"


def test_pkg_refs_resolve_to_overlay_files() -> None:
    from mas.runtime.package_refs import resolve_path_ref

    for name in ("with-hardened.yaml", "observability-native.yaml"):
        path = resolve_path_ref(f"pkg://mas.library.standard/overlays/{name}", Path.cwd())
        assert path.is_file(), path
        assert path.name == name


def test_hardened_stacks_on_existing_governance() -> None:
    from mas.ctl.overlay.merge import merge_overlay

    overlay = yaml.safe_load((OVERLAYS / "with-hardened.yaml").read_text(encoding="utf-8"))
    base = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "telemetry"},
        "spec": {"governance": ["sample_governance"], "tools": ["get_metrics"]},
    }
    merged = merge_overlay(base, overlay)
    names = [g if isinstance(g, str) else next(iter(g)) for g in merged["spec"]["governance"]]
    assert names == ["sample_governance", "gov_no_undeclared_tool"]


def test_hardened_then_native_keeps_both_patches() -> None:
    from mas.ctl.overlay.merge import merge_overlay

    hardened = yaml.safe_load((OVERLAYS / "with-hardened.yaml").read_text(encoding="utf-8"))
    native = yaml.safe_load((OVERLAYS / "observability-native.yaml").read_text(encoding="utf-8"))
    base = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "telemetry"},
        "spec": {"governance": ["sample_governance"]},
    }
    merged = merge_overlay(merge_overlay(base, hardened), native)
    gov = [g if isinstance(g, str) else next(iter(g)) for g in merged["spec"]["governance"]]
    assert "gov_no_undeclared_tool" in gov
    assert merged["spec"]["observability"]
