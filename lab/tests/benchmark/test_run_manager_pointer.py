#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from mas.lab.benchmark.run_manager.pointer import last_run_write_path, resolve_last_run_file


def _pin_xdg(fake_home: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(fake_home / ".local" / "state"))


def test_resolve_last_run_file_uses_xdg_state(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    _pin_xdg(fake_home, monkeypatch)

    canonical = fake_home / ".local" / "state" / "mas"
    canonical.mkdir(parents=True)
    canonical_file = canonical / "last-run.json"
    canonical_file.write_text('{"run_dir": "/canonical"}', encoding="utf-8")

    assert resolve_last_run_file() == canonical_file
    assert last_run_write_path() == canonical_file


def test_resolve_last_run_file_missing_returns_none(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    _pin_xdg(fake_home, monkeypatch)

    assert resolve_last_run_file() is None
