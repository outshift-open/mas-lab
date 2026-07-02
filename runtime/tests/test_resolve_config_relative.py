#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from mas.runtime.workspace_config import resolve_config_relative


def test_relative_path_uses_config_directory(tmp_path: Path) -> None:
    config = tmp_path / "project" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("paths:\n  labs_dir: data/labs\n", encoding="utf-8")

    resolved = resolve_config_relative("data/labs", config)
    assert resolved == (tmp_path / "project" / "data" / "labs").resolve()


def test_absolute_path_unchanged(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    absolute = tmp_path / "abs" / "labs"
    absolute.mkdir(parents=True)

    assert resolve_config_relative(str(absolute), config) == absolute.resolve()


def test_tilde_expands_before_relative_join(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    config = fake_home / ".config" / "mas" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("", encoding="utf-8")

    resolved = resolve_config_relative("~/outside", config)
    assert resolved == (fake_home / "outside").resolve()
