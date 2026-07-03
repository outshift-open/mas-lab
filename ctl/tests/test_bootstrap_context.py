#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Bootstrap context injection — spec.context.* and skill resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mas.ctl.session.bootstrap import _apply_manifest_context
from mas.runtime.boundary.context.manifest_context import (
    ContextRefNotFoundError,
    resolve_context_chunk,
)
from mas.runtime.boundary.context.skills import (
    SkillNotFoundError,
    inject_skills_into_context,
    resolve_skill_path,
)
from mas.runtime.driver.mocks import AutoCtxAssembler


def test_apply_manifest_context_reads_context_role():
    ctx = AutoCtxAssembler()
    manifest = {
        "spec": {
            "context": {
                "role": "You are the SRE lead. Delegate before acting.",
                "tool_usage": "Use tools carefully.",
            }
        }
    }
    _apply_manifest_context(ctx, manifest, Path("/tmp/agents"))
    assert any("[role]" in chunk and "SRE lead" in chunk for chunk in ctx.injected_context)
    assert any("[tool_usage]" in chunk for chunk in ctx.injected_context)


def test_apply_manifest_context_reads_context_ref(tmp_path: Path):
    role_file = tmp_path / "role.md"
    role_file.write_text("External role body.", encoding="utf-8")
    ctx = AutoCtxAssembler()
    manifest = {"spec": {"context": {"role": {"ref": "role.md"}}}}
    _apply_manifest_context(ctx, manifest, tmp_path)
    assert ctx.injected_context == ["[role] External role body."]


def test_apply_manifest_context_reads_context_path_string(tmp_path: Path):
    role_file = tmp_path / "prompts" / "role.md"
    role_file.parent.mkdir()
    role_file.write_text("Path string role.", encoding="utf-8")
    ctx = AutoCtxAssembler()
    manifest = {"spec": {"context": {"role": "./prompts/role.md"}}}
    _apply_manifest_context(ctx, manifest, tmp_path)
    assert ctx.injected_context == ["[role] Path string role."]


def test_apply_manifest_context_only_reads_context_chunks():
    ctx = AutoCtxAssembler()
    manifest = {
        "spec": {
            "role": {"instructions": "removed"},
            "intent": "removed",
            "system_prompt": "removed",
        }
    }
    _apply_manifest_context(ctx, manifest, Path("/tmp"))
    assert ctx.injected_context == []


def test_resolve_context_chunk_ref_object(tmp_path: Path):
    path = tmp_path / "chunk.md"
    path.write_text("chunk text", encoding="utf-8")
    assert resolve_context_chunk({"ref": "chunk.md"}, base_dir=tmp_path) == "chunk text"


def test_resolve_context_chunk_missing_ref_raises(tmp_path: Path):
    with pytest.raises(ContextRefNotFoundError, match="missing.md"):
        resolve_context_chunk({"ref": "missing.md"}, base_dir=tmp_path)


def test_resolve_skill_path_finds_skills_subdir_with_hyphen_slug(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "triage-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Triage protocol", encoding="utf-8")

    path = resolve_skill_path("triage_protocol", base_dir=tmp_path)
    assert path is not None
    text_chunks = inject_skills_into_context(
        [],
        {"spec": {"skills": ["triage_protocol"]}},
        base_dir=tmp_path,
    )
    assert len(text_chunks) == 1
    assert "Triage protocol" in text_chunks[0]


def test_inject_skills_uses_app_root_not_agent_dir(tmp_path: Path):
    app_root = tmp_path / "sre-triage"
    agents_dir = app_root / "agents"
    agents_dir.mkdir(parents=True)
    skill_dir = app_root / "skills" / "data-access-protocol"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Data access", encoding="utf-8")

    manifest = {"spec": {"skills": ["data_access_protocol"]}}

    with pytest.raises(SkillNotFoundError):
        inject_skills_into_context([], manifest, base_dir=agents_dir)
    from_app_root = inject_skills_into_context([], manifest, base_dir=app_root)

    assert len(from_app_root) == 1
    assert "Data access" in from_app_root[0]
