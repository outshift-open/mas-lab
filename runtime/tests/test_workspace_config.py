#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from mas.ctl.workspace.config import WorkspaceConfig


def _flavour(ws: WorkspaceConfig) -> str | None:
    runtime = ws._data.get("mas_runtime") or {}
    return runtime.get("flavour") if isinstance(runtime, dict) else None


def test_workspace_walk_up_prefers_nearest_file(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    ws = repo / "mas-workspace.yaml"
    ws.write_text("mas_runtime:\n  flavour: local\n", encoding="utf-8")

    deep = repo / "a" / "b"
    deep.mkdir(parents=True)

    monkeypatch.chdir(deep)
    loaded = WorkspaceConfig.load()
    assert loaded.found is True
    assert _flavour(loaded) == "local"


def test_workspace_global_fallback(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    deep = repo / "x" / "y"
    deep.mkdir(parents=True)

    fake_home = tmp_path / "home"
    global_dir = fake_home / ".mas"
    global_dir.mkdir(parents=True)
    (global_dir / "mas-workspace.yaml").write_text(
        "mas_runtime:\n  flavour: global-local\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(deep)

    loaded = WorkspaceConfig.load()
    assert loaded.found is True
    assert _flavour(loaded) == "global-local"


def test_workspace_explicit_root_overrides_global(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "mas-workspace.yaml").write_text(
        "mas_runtime:\n  flavour: mounted\n",
        encoding="utf-8",
    )

    fake_home = tmp_path / "home"
    global_dir = fake_home / ".mas"
    global_dir.mkdir(parents=True)
    (global_dir / "mas-workspace.yaml").write_text(
        "mas_runtime:\n  flavour: global-local\n",
        encoding="utf-8",
    )

    other = tmp_path / "elsewhere"
    other.mkdir()

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("MAS_WORKSPACE_ROOT", str(workspace))
    monkeypatch.chdir(other)

    loaded = WorkspaceConfig.load()
    assert loaded.found is True
    assert _flavour(loaded) == "mounted"


def test_workspace_explicit_root_skips_global_when_missing(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    fake_home = tmp_path / "home"
    global_dir = fake_home / ".mas"
    global_dir.mkdir(parents=True)
    (global_dir / "mas-workspace.yaml").write_text(
        "mas_runtime:\n  flavour: global-local\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("MAS_WORKSPACE_ROOT", str(workspace))
    monkeypatch.chdir(workspace)

    loaded = WorkspaceConfig.load()
    assert loaded.found is False
