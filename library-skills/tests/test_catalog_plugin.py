#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for SkillCatalogPlugin — ContextContract catalog emission."""

from __future__ import annotations

from pathlib import Path

import pytest

from mas.library.skills.plugins.sk_catalog import SkillCatalogPlugin, attach_skill_catalog_plugin
from mas.runtime.contracts.context_contract import ContextPlacement


def _skill_dir(tmp_path: Path, name: str, description: str, body: str = "## Body") -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def _manifest(skills: list[str]) -> dict:
    return {"spec": {"skills": skills}}


# ---------------------------------------------------------------------------
# collect_context
# ---------------------------------------------------------------------------

def test_catalog_emits_system_skills_part(tmp_path: Path):
    _skill_dir(tmp_path, "code-review", "Reviews Python code for correctness.")
    manifest = _manifest(["code-review"])
    plugin = SkillCatalogPlugin(manifest=manifest, base_dir=tmp_path)

    parts = plugin.collect_context()
    assert len(parts) == 1
    part = parts[0]
    assert part.placement == ContextPlacement.SYSTEM_SKILLS
    assert part.pinned is True
    assert "code-review" in part.content
    assert "Reviews Python code" in part.content
    assert "activate_skill" in part.content  # behavioral instruction


def test_catalog_empty_when_no_skills(tmp_path: Path):
    plugin = SkillCatalogPlugin(manifest=_manifest([]), base_dir=tmp_path)
    assert plugin.collect_context() == []


def test_catalog_skips_missing_ref(tmp_path: Path, caplog):
    import logging
    manifest = _manifest(["nonexistent-skill"])
    with caplog.at_level(logging.WARNING, logger="mas.library.skills"):
        plugin = SkillCatalogPlugin(manifest=manifest, base_dir=tmp_path)
    assert plugin.collect_context() == []
    assert any("not found" in r.message for r in caplog.records)


def test_catalog_skips_skill_without_description(tmp_path: Path, caplog):
    import logging
    skill_dir = tmp_path / "nodesc"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: nodesc\n---\nBody.\n", encoding="utf-8"
    )
    manifest = _manifest(["nodesc"])
    with caplog.at_level(logging.WARNING, logger="agentskills"):
        plugin = SkillCatalogPlugin(manifest=manifest, base_dir=tmp_path)
    assert plugin.collect_context() == []
    # agentskills.discovery logs when description is missing
    assert any("description" in r.message for r in caplog.records)


def test_catalog_multiple_skills(tmp_path: Path):
    _skill_dir(tmp_path, "skill-a", "Skill A description.")
    _skill_dir(tmp_path, "skill-b", "Skill B description.")
    manifest = _manifest(["skill-a", "skill-b"])
    plugin = SkillCatalogPlugin(manifest=manifest, base_dir=tmp_path)

    parts = plugin.collect_context()
    assert len(parts) == 1
    content = parts[0].content
    assert "skill-a" in content
    assert "skill-b" in content
    assert "Skill A description" in content
    assert "Skill B description" in content


def test_registry_populated(tmp_path: Path):
    _skill_dir(tmp_path, "my-skill", "Does something.")
    manifest = _manifest(["my-skill"])
    plugin = SkillCatalogPlugin(manifest=manifest, base_dir=tmp_path)

    assert len(plugin.registry) == 1
    rec = plugin.registry.get("my-skill")
    assert rec is not None
    assert rec.name == "my-skill"
    assert rec.description == "Does something."
    assert rec.path.name == "SKILL.md"


# ---------------------------------------------------------------------------
# attach_skill_catalog_plugin
# ---------------------------------------------------------------------------

class _FakeCtx:
    pass


def test_attach_populates_ctx(tmp_path: Path):
    _skill_dir(tmp_path, "my-skill", "Does something.")
    ctx = _FakeCtx()
    manifest = _manifest(["my-skill"])

    plugin = attach_skill_catalog_plugin(ctx, manifest, tmp_path)

    assert plugin is not None
    # Plugin registered in plugin_collection (catalog + activated-skills plugin)
    assert hasattr(ctx, "plugin_collection")
    assert len(ctx.plugin_collection) == 2  # SkillCatalogPlugin + ActivatedSkillsContextPlugin
    assert hasattr(ctx, "skill_registry")
    assert ctx.skill_registry is plugin.registry
    assert hasattr(ctx, "activated_skills_plugin")


def test_attach_returns_none_when_no_skills(tmp_path: Path):
    ctx = _FakeCtx()
    result = attach_skill_catalog_plugin(ctx, _manifest([]), tmp_path)
    assert result is None
    assert not hasattr(ctx, "plugin_collection")


def test_attach_returns_none_when_all_refs_fail(tmp_path: Path):
    ctx = _FakeCtx()
    result = attach_skill_catalog_plugin(ctx, _manifest(["ghost"]), tmp_path)
    assert result is None
