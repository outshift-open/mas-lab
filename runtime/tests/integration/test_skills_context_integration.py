#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skills context integration."""

from pathlib import Path

from mas.runtime.boundary.context.skills import (
    load_skill_text,
    resolve_skill_path,
    skill_refs_from_manifest,
)


def test_skill_refs_from_context_manager():
    manifest = {"spec": {"context_manager": {"skills": ["skills/demo"]}}}
    assert skill_refs_from_manifest(manifest) == ["skills/demo"]


def test_resolve_and_load_skill_md(tmp_path):
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo skill\nDo the thing.", encoding="utf-8")
    path = resolve_skill_path("skills/demo", base_dir=tmp_path)
    assert path is not None
    text = load_skill_text("skills/demo", base_dir=tmp_path)
    assert text and "Demo skill" in text
