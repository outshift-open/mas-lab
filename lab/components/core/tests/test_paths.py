#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from mas.lab import paths as lab_paths
from mas.runtime.constants import LEGACY_WORKSPACE_CONFIG_FILENAME, WORKSPACE_CONFIG_FILENAME


def _pin_xdg(fake_home: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(fake_home / ".local" / "share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(fake_home / ".cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(fake_home / ".local" / "state"))


def test_resolve_labs_dir_from_project_config_yaml(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    _pin_xdg(fake_home, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / WORKSPACE_CONFIG_FILENAME).write_text(
        "paths:\n  labs_dir: data/benchmarks\n  cache_dir: data/cache\n  runs_dir: data/runs\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)
    monkeypatch.delenv("MAS_LABS_ROOT", raising=False)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)

    resolved = lab_paths.resolve_path("labs_dir")
    assert resolved.path == (repo / "data/benchmarks").resolve()
    assert resolved.source == WORKSPACE_CONFIG_FILENAME


def test_legacy_mas_workspace_yaml_is_ignored(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / LEGACY_WORKSPACE_CONFIG_FILENAME).write_text("paths:\n  labs_dir: legacy-out\n", encoding="utf-8")
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    _pin_xdg(fake_home, monkeypatch)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("MAS_LABS_ROOT", raising=False)
    monkeypatch.delenv("MAS_DATA_ROOT", raising=False)

    resolved = lab_paths.resolve_path("labs_dir")
    assert resolved.source == lab_paths.DEFAULT_PATH_SOURCE


def test_user_config_fallback(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "mas"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text(
        "labs_dir: custom/labs\n",
        encoding="utf-8",
    )
    other = tmp_path / "nowhere"
    other.mkdir()
    _pin_xdg(fake_home, monkeypatch)
    monkeypatch.chdir(other)
    monkeypatch.delenv("MAS_LABS_ROOT", raising=False)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)

    resolved = lab_paths.resolve_path("labs_dir")
    assert resolved.path == (config_dir / "custom/labs").resolve()
    assert resolved.source == lab_paths.USER_CONFIG_SOURCE


def test_user_config_relative_path_resolves_from_config_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    config_dir = fake_home / ".config" / "mas"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("labs_dir: custom/labs\n", encoding="utf-8")
    other = tmp_path / "nowhere"
    other.mkdir()
    _pin_xdg(fake_home, monkeypatch)
    monkeypatch.chdir(other)
    monkeypatch.delenv("MAS_LABS_ROOT", raising=False)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)

    resolved = lab_paths.resolve_path("labs_dir")
    assert resolved.path == (config_dir / "custom/labs").resolve()
    assert resolved.source == lab_paths.USER_CONFIG_SOURCE


def test_default_paths_use_xdg_layout(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    other = tmp_path / "nowhere"
    other.mkdir()
    _pin_xdg(fake_home, monkeypatch)
    monkeypatch.chdir(other)
    monkeypatch.delenv("MAS_LABS_ROOT", raising=False)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("MAS_DATA_ROOT", raising=False)
    monkeypatch.delenv("MAS_TRACE_CACHE", raising=False)
    monkeypatch.delenv("MAS_LAB_DATA", raising=False)

    assert lab_paths.labs_root() == fake_home / ".local" / "share" / "mas" / "labs"
    assert lab_paths.trace_cache() == fake_home / ".cache" / "mas" / "traces"


def test_trace_cache_honours_workspace_cache_dir(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / WORKSPACE_CONFIG_FILENAME).write_text("paths:\n  cache_dir: data/cache\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("MAS_TRACE_CACHE", raising=False)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)

    assert lab_paths.trace_cache() == (repo / "data/cache/traces").resolve()


def test_trace_cache_honours_mas_data_root(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    data_root = tmp_path / "data-root"
    other = tmp_path / "nowhere"
    other.mkdir()
    _pin_xdg(fake_home, monkeypatch)
    monkeypatch.setenv("MAS_DATA_ROOT", str(data_root))
    monkeypatch.chdir(other)
    monkeypatch.delenv("MAS_TRACE_CACHE", raising=False)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)

    assert lab_paths.trace_cache() == (data_root / "data" / "trace-cache").resolve()


def test_data_cache_uses_cache_dir_under_mas_data_root(tmp_path, monkeypatch):
    data_root = tmp_path / "data-root"
    other = tmp_path / "nowhere"
    other.mkdir()
    monkeypatch.setenv("MAS_DATA_ROOT", str(data_root))
    monkeypatch.chdir(other)
    monkeypatch.delenv("MAS_DATA_CACHE", raising=False)
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)

    assert lab_paths.data_cache() == (data_root / "data" / "cache").resolve()


def test_source_tag_matches_resolve_path_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MAS_LABS_ROOT", str(tmp_path / "labs"))
    monkeypatch.delenv("MAS_WORKSPACE_ROOT", raising=False)
    assert lab_paths.source_tag(key="labs_dir", specific_env="MAS_LABS_ROOT") == "$MAS_LABS_ROOT"
    assert lab_paths.source_tag(key="cache_dir") == lab_paths.resolve_path("cache_dir").source
