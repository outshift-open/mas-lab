#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from mas.lab.benchmark.pipeline import get_step, list_steps, resolve_step_class


def test_get_step_from_manifest() -> None:
    cls = get_step("serialize")
    assert cls is not None
    assert cls.__name__ == "SerializeStep"


def test_list_registered_loads_manifest_steps() -> None:
    items = list_steps()
    assert "serialize" in items
    assert "export_otel" in items


def test_resolve_class_from_python_file(tmp_path: Path):
    mod = tmp_path / "custom_step.py"
    mod.write_text(
        "class MyStep:\n"
        "    pass\n",
        encoding="utf-8",
    )
    cls = resolve_step_class(f"{mod}:MyStep")
    assert cls.__name__ == "MyStep"
