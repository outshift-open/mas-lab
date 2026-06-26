#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill document loading for context injection."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def skill_refs_from_manifest(manifest: dict | None) -> list[str]:
    if not manifest:
        return []
    spec = manifest.get("spec") or {}
    cm = spec.get("context_manager") or {}
    skills = cm.get("skills")
    if skills is None:
        skills = spec.get("skills")
    if not skills:
        return []
    if isinstance(skills, list):
        return [str(s) for s in skills if s]
    return []


def resolve_skill_path(ref: str, *, base_dir: Path) -> Path | None:
    raw = ref.strip()
    if raw.startswith("@"):
        # @lib/bundle/path — resolved by ctl workspace libraries at bootstrap
        return None
    path = (base_dir / raw).resolve()
    if path.is_file():
        return path
    if path.is_dir():
        skill_md = path / "SKILL.md"
        if skill_md.is_file():
            return skill_md
    return None


def load_skill_text(ref: str, *, base_dir: Path) -> str | None:
    path = resolve_skill_path(ref, base_dir=base_dir)
    if path is None:
        return None
    return path.read_text(encoding="utf-8").strip()


def build_skill_plugin(**kwargs: Any) -> dict[str, Any]:
    """Registry hook — skills are injected via bootstrap context pipeline."""
    return dict(kwargs)


def inject_skills_into_context(
    injected: list[str],
    manifest: dict | None,
    *,
    base_dir: Path,
) -> list[str]:
    """Append skill documents to context assembly (SYSTEM_SKILLS band)."""
    out = list(injected)
    for ref in skill_refs_from_manifest(manifest):
        text = load_skill_text(ref, base_dir=base_dir)
        if text:
            out.append(f"[skill:{ref}]\n{text}")
    return out
