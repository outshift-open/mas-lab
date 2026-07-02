#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill document loading for context injection."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SkillNotFoundError(FileNotFoundError):
    """Raised when a manifest skill ref cannot be resolved on disk."""


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


def _skill_search_roots(base_dir: Path) -> list[Path]:
    roots = [base_dir]
    skills_dir = base_dir / "skills"
    if skills_dir.is_dir():
        roots.append(skills_dir)
    return roots


def _skill_leaf_name(ref: str) -> str:
    return ref.strip().strip("/").removeprefix("skills/")


def resolve_skill_path(ref: str, *, base_dir: Path) -> Path | None:
    raw = ref.strip()
    if raw.startswith("@"):
        # @lib/bundle/path — resolved by ctl workspace libraries at bootstrap
        return None
    name = _skill_leaf_name(raw)
    if not name:
        return None
    for root in _skill_search_roots(base_dir):
        direct = (root / name).resolve()
        if direct.is_file():
            return direct
        if direct.is_dir():
            skill_md = direct / "SKILL.md"
            if skill_md.is_file():
                return skill_md
        skill_md = (root / name / "SKILL.md").resolve()
        if skill_md.is_file():
            return skill_md
    return None


def load_skill_text(ref: str, *, base_dir: Path) -> str:
    path = resolve_skill_path(ref, base_dir=base_dir)
    if path is None:
        raise SkillNotFoundError(
            f"Skill {ref!r} not found under {base_dir} (searched app root and skills/)"
        )
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
        out.append(f"[skill:{ref}]\n{text}")
    return out
