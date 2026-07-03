#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for nested lab artifact discovery and MAS schema validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from mas.lab.controller.lab_registry import LabRegistry, reset_lab_registry
from mas.lab.controller.manifest_store import ManifestStore


@pytest.fixture
def nested_lab(tmp_path: Path) -> Path:
    """Mirror design-space.lab layout: sub-modules with nested artifacts."""
    lab = tmp_path / "design-space.lab"
    mod1 = lab / "01-design-patterns"
    mod2 = lab / "02-topologies"
    for mod in (mod1, mod2):
        (mod / "overlays").mkdir(parents=True)
        (mod / "flavours").mkdir()
        (mod / "datasets").mkdir()
        (mod / "infra").mkdir()
        (mod / "overlays" / f"{mod.name}.yaml").write_text(
            f"apiVersion: mas/v1\nkind: Overlay\nmetadata:\n  name: {mod.name}\n"
            f"  description: overlay for {mod.name}\n",
            encoding="utf-8",
        )
        (mod / "flavours" / "local.yaml").write_text(
            f"metadata:\n  name: local-{mod.name}\n",
            encoding="utf-8",
        )
        (mod / "datasets" / f"{mod.name}-queries.yaml").write_text(
            f"apiVersion: lab/v1\nkind: Dataset\nmetadata:\n  name: {mod.name}-queries\n"
            f"spec:\n  items: []\n",
            encoding="utf-8",
        )
        (mod / "experiment.yaml").write_text(
            f"experiment:\n  name: exp-{mod.name}\n  description: {mod.name}\n",
            encoding="utf-8",
        )
        (mod / "pipeline-figure.yaml").write_text(
            "pipeline:\n  name: pipeline-figure\n  steps: []\n",
            encoding="utf-8",
        )

    app_dir = lab / "apps" / "qa-agent"
    app_dir.mkdir(parents=True)
    agents = app_dir / "agents"
    agents.mkdir()
    (agents / "qa-agent.yaml").write_text(
        "apiVersion: mas/v1\nkind: Agent\nmetadata:\n  name: qa-agent\nspec:\n  models: []\n",
        encoding="utf-8",
    )
    return lab


def test_schema_discovery_custom_filenames(tmp_path: Path):
    """Any YAML name works when the document matches the experiment schema."""
    lab = tmp_path / "custom.lab"
    mod = lab / "study-a"
    mod.mkdir(parents=True)
    (mod / "my-study.yaml").write_text(
        "experiment:\n  name: custom-study\n  description: arbitrary filename\n",
        encoding="utf-8",
    )
    (mod / "figure-flow.yaml").write_text(
        "pipeline:\n  metadata:\n    name: figure-flow\n  steps: []\n",
        encoding="utf-8",
    )

    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"custom": lab}

    exps = reg.list_experiments("custom")
    assert len(exps) == 1
    assert exps[0]["name"] == "custom-study"
    assert exps[0]["path"] == "study-a/my-study.yaml"

    pipes = reg.list_pipelines("custom")
    assert len(pipes) == 1
    assert pipes[0]["name"] == "figure-flow"
    reset_lab_registry()


def test_nested_experiments_pipelines_overlays_datasets(nested_lab: Path):
    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"design-space": nested_lab}

    exps = reg.list_experiments("design-space")
    assert len(exps) == 2
    assert {e["name"] for e in exps} == {"exp-01-design-patterns", "exp-02-topologies"}
    assert all("01-design-patterns" in e["path"] or "02-topologies" in e["path"] for e in exps)

    pipes = reg.list_pipelines("design-space")
    assert len(pipes) == 2
    assert pipes[0]["path"] != pipes[1]["path"]

    overlays = reg.list_overlays("design-space")
    assert len(overlays) == 2
    assert {o["name"] for o in overlays} == {"01-design-patterns", "02-topologies"}

    datasets = reg.list_datasets("design-space")
    assert len(datasets) == 2
    assert all("datasets/" in d["path"] for d in datasets)

    reset_lab_registry()


def test_nested_mas_yaml_discovery(nested_lab: Path):
    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"design-space": nested_lab}

    resources = reg.collect_mas_resources("design-space")
    assert "qa-agent" in resources
    assert resources["qa-agent"]["path"] == "apps/qa-agent/agents/qa-agent.yaml"
    reset_lab_registry()


def test_lab_library_includes_workspace_apps(nested_lab: Path, monkeypatch):
    """*.lab libraries expose installed sample apps in Applications tab."""
    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"design-space": nested_lab}
    monkeypatch.setattr(
        reg,
        "runtime_objects",
        lambda kind: {"trip-planner": nested_lab / "apps" / "trip-planner"}
        if kind == "app"
        else {},
    )
    (nested_lab / "apps" / "trip-planner").mkdir(parents=True, exist_ok=True)
    (nested_lab / "apps" / "trip-planner" / "mas.yaml").write_text(
        "apiVersion: mas/v1\nkind: MAS\nmetadata:\n  name: trip-planner\nspec:\n  agency:\n    agents: []\n",
        encoding="utf-8",
    )

    resources = reg.collect_mas_resources("design-space")
    assert "qa-agent" in resources
    assert "trip-planner" in resources
    reset_lab_registry()


def test_config_files_include_workspace_infra(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "infra").mkdir()
    (ws / "infra" / "llm-proxy.yaml").write_text(
        "apiVersion: infra/v1\nkind: LLMProxy\nmetadata:\n  name: proxy\n",
        encoding="utf-8",
    )
    lab = ws / "labs" / "demo.lab"
    lab.mkdir(parents=True)

    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"demo": lab}
    monkeypatch_ws = type("Ws", (), {"_path": ws, "_data": {}})()
    reg._workspace = monkeypatch_ws

    from mas.lab.controller.manifest_store import ManifestStore

    store = ManifestStore(monkeypatch_ws)
    store._libraries = {"demo": lab}
    configs = store.config_files("demo")
    assert any(k.startswith("workspace/infra/") for k in configs["infra"])
    assert "config.yaml" not in configs["workspace"] or configs["workspace"] == {}
    reset_lab_registry()


def test_list_all_experiments_across_libraries(tmp_path: Path):
    lab_a = tmp_path / "a.lab"
    lab_b = tmp_path / "b.lab"
    for lab, name in ((lab_a, "exp-a"), (lab_b, "exp-b")):
        lab.mkdir()
        (lab / "experiment.yaml").write_text(
            f"experiment:\n  name: {name}\n  description: {name}\n",
            encoding="utf-8",
        )

    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"a": lab_a, "b": lab_b}
    all_exps = reg.list_all_experiments()
    assert len(all_exps) == 2
    assert {e["library"] for e in all_exps} == {"a", "b"}
    reset_lab_registry()


def test_manifest_store_config_files_nested(nested_lab: Path):
    store = ManifestStore(workspace=None)
    store._libraries = {"design-space": nested_lab}

    configs = store.config_files("design-space")
    flavour_keys = list(configs["flavours"])
    assert len(flavour_keys) == 2
    assert any(k.startswith("01-design-patterns/flavours/") for k in flavour_keys)
    assert any(k.startswith("02-topologies/flavours/") for k in flavour_keys)


def test_design_space_datasets_symlinks():
    """Design-space lab exposes benchmark datasets via datasets/ symlinks."""
    repo_root = Path(__file__).resolve().parents[4]
    lab_path = repo_root / "labs" / "design-space.lab"
    if not lab_path.is_dir():
        pytest.skip("repo labs/ not present")

    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"design-space": lab_path}
    datasets = reg.list_datasets("design-space")
    names = {d["name"] for d in datasets}
    assert "qa-reasoning-queries-100.yaml" in names
    assert "trip-planner-benchmark-100.yaml" in names
    reset_lab_registry()


def test_real_repo_design_space_discovery():
    """Integration: actual labs/design-space.lab on disk when tests run from repo."""
    repo_root = Path(__file__).resolve().parents[4]
    lab_path = repo_root / "labs" / "design-space.lab"
    if not lab_path.is_dir():
        pytest.skip("repo labs/ not present")

    reset_lab_registry()
    reg = LabRegistry()
    reg._libraries = {"design-space": lab_path}

    overlays = reg.list_overlays("design-space")
    assert len(overlays) >= 10

    datasets = reg.list_datasets("design-space")
    assert len(datasets) >= 2

    reset_lab_registry()


def test_canvas_mas_manifest_passes_schema():
    """UI canvas output must validate against runtime mas.schema.yaml."""
    from mas.ctl.validate import validate_data

    manifest = {
        "apiVersion": "mas/v1",
        "kind": "MAS",
        "metadata": {"name": "test-mas"},
        "spec": {
            "agents": [{"id": "broker", "ref": "test-mas/broker.yaml"}],
            "workflow": {
                "type": "dynamic",
                "entry": "broker",
                "nodes": [{"id": "broker", "role": "moderator"}],
            },
        },
        "x-canvas-positions": {"node-1": {"x": 10, "y": 20}},
    }

    result = validate_data(manifest, kind="mas")
    assert result.ok, [f"{i.path}: {i.message}" for i in result.issues if i.level == "error"]


def test_all_registered_libraries_have_experiments_when_present():
    """Each *.lab under repo labs/ should expose experiments via registry."""
    repo_root = Path(__file__).resolve().parents[4]
    labs_dir = repo_root / "labs"
    if not labs_dir.is_dir():
        pytest.skip("repo labs/ not present")

    reset_lab_registry()
    reg = LabRegistry()
    for path in sorted(labs_dir.glob("*.lab")):
        slug = path.stem
        reg._libraries[slug] = path
        exps = reg.list_experiments(slug)
        assert len(exps) >= 1, f"{slug} should expose at least one experiment"
    reset_lab_registry()
