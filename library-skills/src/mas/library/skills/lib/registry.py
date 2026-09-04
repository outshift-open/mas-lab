
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill registry — in-memory map of name → SkillRecord.

Built by SkillCatalogPlugin at session start (ctx_collect_execute) and shared
with SkillToolsPlugin via ``ctx.skill_registry`` so both plugins reference
exactly the same resolved paths without re-scanning the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SkillRecord:
    """Immutable record for a discovered, validated skill.

    Required fields (agentskills.io spec §Frontmatter):
        name, description, path

    Optional spec fields stored for downstream use:
        compatibility — environment requirements (logged by activate_skill)
        license       — license name or reference
        tags          — keyword list from frontmatter
        source_scope  — discovery scope: 'project', 'user', or 'builtin'
    """

    name: str
    description: str
    path: Path  # absolute path to SKILL.md

    # Optional spec fields
    compatibility: str | None = None
    license: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    source_scope: str = "project"  # 'project' | 'user' | 'builtin'

    # Spec fields: metadata map (stored as immutable tuple of pairs)
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # Spec field: allowed-tools (experimental pre-approved tools list)
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)

    @property
    def metadata_dict(self) -> dict[str, str]:
        """metadata as a regular dict (for downstream consumers)."""
        return dict(self.metadata)

    @property
    def base_dir(self) -> Path:
        """Parent directory of SKILL.md — root for relative resource paths."""
        return self.path.parent


class SkillRegistry:
    """In-memory map of skill name → SkillRecord.

    Populated once per session by SkillCatalogPlugin; read by SkillToolsPlugin.
    Thread-safety is not required: population happens synchronously in bootstrap
    before any concurrent tool calls can arrive.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillRecord] = {}

    def register(self, record: SkillRecord) -> None:
        """Register a skill; silently replaces an existing record with the same name."""
        self._skills[record.name] = record

    def get(self, name: str) -> SkillRecord | None:
        """Return the SkillRecord for *name*, or ``None`` if not found."""
        return self._skills.get(name)

    def all(self) -> list[SkillRecord]:
        """Return all registered records in registration order."""
        return list(self._skills.values())

    def names(self) -> list[str]:
        return list(self._skills)

    def __len__(self) -> int:
        return len(self._skills)

    def __bool__(self) -> bool:
        return bool(self._skills)
