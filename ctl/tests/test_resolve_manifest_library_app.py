#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from mas.ctl.paths import resolve_manifest


def test_resolve_manifest_library_app(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "library-ioc"
    app = root / "apps" / "sre-triage" / "v2"
    app.mkdir(parents=True)
    (root / "library.yaml").write_text(
        "apiVersion: mas/v1\nkind: Library\nname: mas-library-ioc\n"
        "apps:\n  sre-triage: apps/sre-triage\n",
        encoding="utf-8",
    )
    mas = app / "mas.yaml"
    mas.write_text(
        "apiVersion: mas/v1\nkind: MAS\nmetadata:\n  name: sre-triage\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAS_LIBRARY_PATHS", str(root))

    resolved = resolve_manifest("library-ioc:sre-triage@v2", cwd=tmp_path)
    assert resolved == mas.resolve()
    assert resolve_manifest("library-ioc:apps/sre-triage/v2", cwd=tmp_path) == mas.resolve()
