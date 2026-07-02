#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skills context integration."""

from pathlib import Path

import pytest

from mas.runtime.boundary.context.skills import (
    SkillNotFoundError,
    inject_skills_into_context,
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
    assert "Demo skill" in text


def test_resolve_skill_exact_name_under_skills_dir(tmp_path):
    skill_dir = tmp_path / "skills" / "triage-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Triage", encoding="utf-8")
    path = resolve_skill_path("triage-protocol", base_dir=tmp_path)
    assert path is not None
    assert path.name == "SKILL.md"


def test_resolve_skill_rejects_name_mismatch(tmp_path):
    skill_dir = tmp_path / "skills" / "triage-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Triage", encoding="utf-8")
    assert resolve_skill_path("triage_protocol", base_dir=tmp_path) is None


def test_inject_skills_raises_when_missing(tmp_path):
    manifest = {"spec": {"skills": ["missing-skill"]}}
    with pytest.raises(SkillNotFoundError, match="missing-skill"):
        inject_skills_into_context([], manifest, base_dir=tmp_path)


def test_inject_skills_app_root_layout(tmp_path):
    app = tmp_path / "sre-triage"
    skill_dir = app / "skills" / "triage-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("protocol", encoding="utf-8")
    manifest = {"spec": {"skills": ["triage-protocol"]}}
    injected = inject_skills_into_context([], manifest, base_dir=app)
    assert any("protocol" in chunk for chunk in injected)
