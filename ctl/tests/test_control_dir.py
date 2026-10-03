#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from mas.ctl.session.control_dir import default_control_dir


def test_mas_control_dir_overrides(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "override"
    monkeypatch.setenv("MAS_CONTROL_DIR", str(target))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert default_control_dir() == target
    assert target.is_dir()


def test_xdg_runtime_dir_is_preferred(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.delenv("MAS_CONTROL_DIR", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    assert default_control_dir() == runtime / "mas-ctl"
