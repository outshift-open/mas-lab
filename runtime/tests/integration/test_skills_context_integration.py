#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skills context integration — fully in library-skills; no runtime skill imports."""

from pathlib import Path

from mas.library.skills.lib.resolver import resolve_skill_path
from mas.library.skills.lib.spec import skill_refs_from_manifest
from mas.library.skills.plugins.sk_catalog import SkillCatalogPlugin, attach_skill_catalog_plugin


def test_skill_refs_from_manifest():
    manifest = {"spec": {"skills": ["skills/demo"]}}
    assert skill_refs_from_manifest(manifest) == ["skills/demo"]


def test_resolve_and_load_skill_md(tmp_path):
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill.\n---\n# Demo skill\nDo the thing.",
        encoding="utf-8",
    )
    path = resolve_skill_path("skills/demo", base_dir=tmp_path)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "Demo skill" in text


def test_resolve_skill_exact_name_under_skills_dir(tmp_path):
    skill_dir = tmp_path / "skills" / "triage-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: triage-protocol\ndescription: Triage.\n---\n# Triage",
        encoding="utf-8",
    )
    path = resolve_skill_path("triage-protocol", base_dir=tmp_path)
    assert path is not None
    assert path.name == "SKILL.md"


def test_resolve_skill_normalizes_underscore_slug(tmp_path):
    skill_dir = tmp_path / "skills" / "triage-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: triage-protocol\ndescription: Triage.\n---\n# Triage",
        encoding="utf-8",
    )
    path = resolve_skill_path("triage_protocol", base_dir=tmp_path)
    assert path is not None
    assert path.name == "SKILL.md"


def test_catalog_plugin_missing_ref_returns_empty(tmp_path):
    manifest = {"spec": {"skills": ["missing-skill"]}}
    plugin = SkillCatalogPlugin(manifest=manifest, base_dir=tmp_path)
    assert plugin.collect_context() == []


def test_catalog_plugin_injects_catalog_only(tmp_path):
    app = tmp_path / "sre-triage"
    skill_dir = app / "skills" / "triage-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: triage-protocol\ndescription: Handles triage.\n---\n# Body content",
        encoding="utf-8",
    )
    manifest = {"spec": {"skills": ["triage-protocol"]}}
    plugin = SkillCatalogPlugin(manifest=manifest, base_dir=app)
    parts = plugin.collect_context()
    assert len(parts) == 1
    assert "triage-protocol" in parts[0].content
    assert "Handles triage" in parts[0].content
    assert "# Body content" not in parts[0].content


def test_attach_populates_ctx_skill_registry(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Does something.\n---\n# Body",
        encoding="utf-8",
    )

    class _Ctx:
        pass

    ctx = _Ctx()
    manifest = {"spec": {"skills": ["my-skill"]}}
    plugin = attach_skill_catalog_plugin(ctx, manifest, tmp_path)
    assert plugin is not None
    assert ctx.skill_registry is plugin.registry
    assert ctx.skill_registry.get("my-skill") is not None
    # plugin_collection has both catalog + activated-skills plugin
    assert hasattr(ctx, "plugin_collection")
    assert len(ctx.plugin_collection) == 2
