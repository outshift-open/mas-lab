#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill discovery — locate SKILL.md files in multiple scopes.

Discovers skills in this order:
  1. ``<base_dir>`` and subdirectories
  2. ``<base_dir>/skills/`` and ``<base_dir>/.agents/skills/``
  3. Parent directory skills/ (monorepo walk-up to git root or depth limit)
  4. User-level: ``~/.agents/skills/``, ``~/.{client}/skills/``, ``~/.mas/skills/``

Name normalization: ``foo``, ``foo-bar``, ``foo_bar`` all resolve to the same
skill. Collision detection: first found wins; duplicates logged as WARNING.
"""

from __future__ import annotations

import logging
from pathlib import Path
from subprocess import CalledProcessError, run

from .parsing import parse_skill_frontmatter
from .registry import SkillRecord, SkillRegistry

logger = logging.getLogger(__name__)


class Discovery:
    """Discover and register skills from manifest refs.

    Handles:
    - Multi-scope directory searching (project → user → builtin)
    - Collision detection (first found wins)
    - Disabled filtering (skip skills with disabled: true)
    - Name normalization (foo, foo-bar, foo_bar variants)
    """

    def __init__(
        self,
        manifest_skills: list[str] | None = None,
        base_dir: Path | None = None,
        search_additional: list[Path | str] | None = None,
        client_name: str | None = None,
        ancestor_walk_depth: int | None = None,
    ) -> None:
        """Initialize discovery.

        Args:
            manifest_skills: List of skill refs from the agent manifest.
            base_dir: Root directory for skill resolution (default: current dir).
            search_additional: Extra directories to search (prepended path).
            client_name: Client identifier (e.g. "mas-lab") for user dir scan.
            ancestor_walk_depth: Max directory levels to walk (None = git root).
        """
        self.manifest_skills = manifest_skills or []
        self.base_dir = Path(base_dir or Path.cwd()).resolve()
        self.search_additional = [Path(p).resolve() for p in (search_additional or [])]
        self.client_name = client_name
        self.ancestor_walk_depth = ancestor_walk_depth
        self.registry = SkillRegistry()
        self._discovered_names: set[str] = set()

    def discover(self) -> SkillRegistry:
        """Discover and register all skills.

        Returns the populated SkillRegistry.
        Logs WARNINGs for collisions (duplicate names); first found wins.
        Logs WARNINGs for missing/malformed skills.
        """
        for ref in self.manifest_skills:
            self._discover_one(ref)
        return self.registry

    def _discover_one(self, ref: str) -> None:
        """Discover a single skill ref and register it."""
        # Resolve path
        skill_path = self._resolve_skill_path(ref)
        if not skill_path:
            logger.warning(f"Skill ref not found: {ref}")
            return

        # Read and parse
        try:
            text = skill_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning(f"Failed to read skill {ref}: {e}")
            return

        metadata, _body = parse_skill_frontmatter(text)

        # Extract required fields
        name = metadata.get("name", "").strip()
        if not name:
            logger.warning(f"Skill {ref} missing required field: name")
            return
        description = metadata.get("description", "").strip()
        if not description:
            logger.warning(f"Skill {ref} missing required field: description")
            return

        # Check disabled flag
        if metadata.get("disabled"):
            logger.debug(f"Skill {name} is disabled, skipping")
            return

        # Collision detection
        if name in self._discovered_names:
            logger.warning(
                f"Skill collision: {name} (from {skill_path}) already registered; "
                "skipping"
            )
            return

        # Extract optional fields
        compatibility = metadata.get("compatibility")
        license_val = metadata.get("license")
        tags = tuple(str(t).strip() for t in metadata.get("tags", []) if t)
        metadata_pairs = tuple(
            (str(k), str(v))
            for k, v in metadata.get("metadata", {}).items()
            if k and v
        )
        allowed_tools = tuple(
            str(t).strip() for t in metadata.get("allowed_tools", []) if t
        )

        # Determine source scope
        source_scope = self._classify_scope(skill_path)

        # Create record and register
        record = SkillRecord(
            name=name,
            description=description,
            path=skill_path,
            compatibility=compatibility,
            license=license_val,
            tags=tags,
            source_scope=source_scope,
            metadata=metadata_pairs,
            allowed_tools=allowed_tools,
        )
        self.registry.register(record)
        self._discovered_names.add(name)

    def _resolve_skill_path(self, ref: str) -> Path | None:
        """Resolve a skill ref to its SKILL.md path, or None if not found."""
        raw = ref.strip()
        if raw.startswith("@"):
            logger.debug(
                "Skill ref %r is library-scoped (@…); not resolved locally", raw
            )
            return None

        # Try name variants (foo, foo-bar, foo_bar)
        for name in _skill_name_variants(raw):
            for root in self._skill_search_roots():
                # Try direct file or directory with SKILL.md
                direct = (root / name).resolve()
                if direct.is_file():
                    return direct
                if direct.is_dir():
                    skill_md = direct / "SKILL.md"
                    if skill_md.is_file():
                        return skill_md

        return None

    def _skill_search_roots(self) -> list[Path]:
        """Return ordered list of directories to search for skills."""
        seen: dict[Path, None] = {}

        def _add(p: Path) -> None:
            r = p.resolve()
            if r not in seen and r.exists():
                seen[r] = None

        # Additional search paths (prepended, highest priority)
        for p in self.search_additional:
            _add(p)

        # Project-level directories
        _add(self.base_dir)
        _add(self.base_dir / "skills")
        _add(self.base_dir / ".agents" / "skills")

        # Ancestor-dir scan (monorepo walk-up)
        self._walk_ancestors(self.base_dir, seen)

        # User-level directories
        home = Path.home()
        _add(home / ".agents" / "skills")
        if self.client_name:
            _add(home / f".{self.client_name}" / "skills")
        _add(home / ".mas" / "skills")

        return [p for p in seen]

    def _walk_ancestors(self, start: Path, seen: dict[Path, None]) -> None:
        """Walk up the directory tree looking for skills/ directories.

        Stops at git root (or after ancestor_walk_depth levels, if set).
        """
        try:
            git_root = Path(
                run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=start,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
            ).resolve()
        except CalledProcessError:
            git_root = None

        for depth, parent in enumerate(start.resolve().parents):
            # Stop at git root or depth limit
            if git_root and parent == git_root:
                break
            if (
                self.ancestor_walk_depth is not None
                and depth > self.ancestor_walk_depth
            ):
                break

            p_skills = parent / "skills"
            r = p_skills.resolve()
            if r not in seen and r.exists():
                seen[r] = None

    def _classify_scope(self, skill_path: Path) -> str:
        """Classify skill as 'project', 'user', or 'builtin'."""
        home = Path.home()
        skill_resolved = skill_path.resolve()

        if skill_resolved.is_relative_to(home):
            return "user"
        if skill_resolved.is_relative_to(self.base_dir):
            return "project"
        return "builtin"


def _skill_name_variants(ref: str) -> list[str]:
    """Return lookup name variants for *ref* (dash/underscore normalisation)."""
    leaf = _skill_leaf_name(ref)
    if not leaf:
        return []
    return list(dict.fromkeys([leaf, leaf.replace("_", "-"), leaf.replace("-", "_")]))


def _skill_leaf_name(ref: str) -> str:
    """Strip namespace prefixes so ``skills/foo`` and ``global/foo`` → ``foo``."""
    return (
        ref.strip()
        .strip("/")
        .removeprefix("skills/")
        .removeprefix("global/")
    )
