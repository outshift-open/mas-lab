#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill path resolution — discover SKILL.md files from manifest refs.

Skill path resolution lives entirely in library-skills (not in the runtime).
The runtime has no knowledge of skill directory layout or SKILL.md conventions.

Resolution order for a ref ``foo``:
  1. ``<base_dir>/foo``                (direct file or dir with SKILL.md)
  2. ``<base_dir>/skills/foo``         (app-level skills/ subfolder)
  3. ``<base_dir>/.agents/skills/foo`` (cross-client convention, project-level)
  4. ``<parent>/skills/foo``           (library-level skills/ — walk up once)
  5. ``~/.agents/skills/foo``          (user-level cross-client convention)
  6. ``~/.mas/skills/foo``             (MAS Lab user-level skills)

Name variants: ``foo``, ``foo-bar`` ↔ ``foo_bar`` (dash/underscore swap).
"""

from __future__ import annotations

from pathlib import Path


def skill_search_roots(base_dir: Path) -> list[Path]:
    """Return ordered list of directories to search for skill subdirectories.

    Includes the project-level ``.agents/skills/`` directory (cross-client
    convention) and user-level ``~/.agents/skills/`` and ``~/.mas/skills/``.
    """
    seen: dict[Path, None] = {}

    def _add(p: Path) -> None:
        r = p.resolve()
        if r not in seen:
            seen[r] = None

    _add(base_dir)
    _add(base_dir / "skills")
    # Cross-client convention: project-level .agents/skills/
    _add(base_dir / ".agents" / "skills")

    # Walk up once to find a library-level skills/ shared across apps
    for parent in base_dir.resolve().parents:
        p_skills = parent / "skills"
        if p_skills.is_dir() and p_skills.resolve() not in seen:
            _add(p_skills)
            break

    # User-level skill directories
    home = Path.home()
    _add(home / ".agents" / "skills")
    _add(home / ".mas" / "skills")

    return [p for p in seen if p.exists()]


def skill_name_variants(ref: str) -> list[str]:
    """Return lookup name variants for *ref* (dash/underscore normalisation)."""
    leaf = _skill_leaf_name(ref)
    if not leaf:
        return []
    return list(dict.fromkeys([leaf, leaf.replace("_", "-"), leaf.replace("-", "_")]))


def resolve_skill_path(ref: str, *, base_dir: Path) -> Path | None:
    """Resolve a skill ref to its ``SKILL.md`` path, or ``None`` if not found.

    ``@lib/…`` refs (resolved by ctl workspace libraries at bootstrap) are
    passed through as-is and always return ``None`` from this function.
    """
    raw = ref.strip()
    if raw.startswith("@"):
        return None
    for name in skill_name_variants(raw):
        for root in skill_search_roots(base_dir):
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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _skill_leaf_name(ref: str) -> str:
    """Strip namespace prefixes so ``skills/foo`` and ``global/foo`` → ``foo``."""
    return (
        ref.strip()
        .strip("/")
        .removeprefix("skills/")
        .removeprefix("global/")
    )
