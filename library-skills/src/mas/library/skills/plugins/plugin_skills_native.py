#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Native skill plugin — custom implementation (reference baseline).

Design incorporates the best ideas from the ADK and deepagents wrappers:

- **Single-pass caching** (from ADK): SKILL.md is parsed exactly once at
  ``discover()`` time.  ``activate()`` and ``allowed_tools()`` return cached
  data — zero extra disk reads per call.

- **Correct ``allowed-tools`` parsing** (from deepagents): we parse the
  frontmatter ourselves with ``parse_skill_frontmatter`` so the hyphenated
  YAML key ``allowed-tools`` is handled correctly.  This replaces the
  ``_parse_allowed_tools()`` workaround that re-read the file to work around
  agentskills' char-iteration bug.

- **Keeps what no other implementation has**:
  - Ancestor-dir walk via ``agentskills.Discovery`` (project → git root →
    the user's ``.mas-lab/skills/`` directory).
  - POSIX ``rlimit`` sandboxing via ``sandbox.run_script()``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentskills import Discovery, parse_skill_frontmatter
from sandbox import run_script

from .skill_plugin_base import (
    SkillActivation,
    SkillMetadata,
    SkillPlugin,
    guard_resource_realpath,
)

logger = logging.getLogger(__name__)


@dataclass
class _SkillEntry:
    """Pre-loaded skill data — ADK-style single-read cache."""

    metadata: SkillMetadata
    body: str               # SKILL.md body, parsed once at discover time
    resources: dict[str, Path]  # resource listing (paths); content still lazy


class NativeSkillPlugin(SkillPlugin):
    """Native skill implementation using python-agentskills + python-sandbox."""

    def __init__(
        self,
        base_dir: Path | None = None,
        working_dir: Path | None = None,
        run_dir: Path | None = None,
    ):
        super().__init__(working_dir=working_dir, run_dir=run_dir)
        self.base_dir = Path(base_dir or Path.cwd()).resolve()
        self._cache: dict[str, _SkillEntry] | None = None

    # ------------------------------------------------------------------
    # Internal: single-pass builder
    # ------------------------------------------------------------------

    def _build_cache(self, base_dir: Path) -> dict[str, _SkillEntry]:
        """Discover skills and pre-parse each SKILL.md exactly once.

        Uses agentskills.Discovery for the scan (ancestor-dir walk, user-level
        dirs).  Then reads every SKILL.md with our own parser so the body and
        ``allowed-tools`` field are correct.
        """
        # agentskills.Discovery is manifest-driven: collect skill names first.
        skill_names = []
        for scan_subdir in ["skills", ".agents/skills"]:
            skill_dir = base_dir / scan_subdir
            if not skill_dir.exists():
                continue
            for subdir in sorted(skill_dir.iterdir()):
                if subdir.is_dir() and (subdir / "SKILL.md").exists():
                    skill_names.append(subdir.name)

        registry = Discovery(
            manifest_skills=skill_names,
            base_dir=base_dir,
        ).discover()

        cache: dict[str, _SkillEntry] = {}

        for record in registry.all():
            skill_dir = record.path.parent  # record.path is the SKILL.md file

            # Parse SKILL.md once — get body AND correct metadata.
            try:
                text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("native: skipping %s — %s", record.name, e)
                continue

            raw_meta, body = parse_skill_frontmatter(text)

            # agentskills has a char-iteration bug on the allowed_tools field;
            # we parse it ourselves from our own frontmatter result instead.
            # The spec uses "allowed-tools" (hyphen); also accept underscore form.
            raw = raw_meta.get("allowed-tools") or raw_meta.get("allowed_tools", "")
            allowed_tools: list[str] | None = None
            if isinstance(raw, str):
                allowed_tools = raw.split() or None
            elif isinstance(raw, (list, tuple)):
                allowed_tools = list(raw) or None

            # Pre-scan resource listing (paths only — content read lazily).
            resources: dict[str, Path] = {}
            for category in ["scripts", "references", "assets"]:
                subpath = skill_dir / category
                if subpath.exists():
                    for file in subpath.rglob("*"):
                        if file.is_file():
                            resources[str(file.relative_to(skill_dir))] = file

            cache[record.name] = _SkillEntry(
                metadata=SkillMetadata(
                    name=record.name,
                    description=record.description,
                    path=skill_dir,
                    license=record.license,
                    compatibility=record.compatibility,
                    allowed_tools=allowed_tools,
                ),
                body=body,
                resources=resources,
            )

        return cache

    def _entry(self, skill_name: str) -> _SkillEntry:
        """Return cached entry; build cache lazily if needed."""
        if self._cache is None:
            self._cache = self._build_cache(self.base_dir)
        entry = self._cache.get(skill_name)
        if not entry:
            msg = f"Skill not found: {skill_name}"
            raise ValueError(msg)
        return entry

    # ------------------------------------------------------------------
    # SkillPlugin interface
    # ------------------------------------------------------------------

    def discover(self, base_dir: Path) -> dict[str, SkillMetadata]:
        """Discover skills via agentskills.Discovery (ancestor-dir walk)."""
        self.base_dir = base_dir
        self._cache = self._build_cache(base_dir)
        return {name: entry.metadata for name, entry in self._cache.items()}

    def activate(self, skill_name: str) -> SkillActivation:
        """Return Tier-2 instructions from cache — no disk read."""
        entry = self._entry(skill_name)
        return SkillActivation(
            name=skill_name,
            body=entry.body,
            resources=entry.resources,
        )

    def read_resource(self, skill_name: str, resource_path: str) -> str:
        """Read a resource file (content is lazy — read on demand)."""
        entry = self._entry(skill_name)
        skill_dir = entry.metadata.path
        file_path = guard_resource_realpath(skill_dir, resource_path)

        if not file_path.exists():
            msg = f"Resource not found: {resource_path}"
            raise FileNotFoundError(msg)

        return file_path.read_text(encoding="utf-8")

    def run_script(
        self,
        skill_name: str,
        script_name: str,
        args: list[str] | None = None,
        timeout: int = 30,
        env_extra: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a script via sandbox.run_script() (POSIX rlimit)."""
        entry = self._entry(skill_name)
        skill_dir = entry.metadata.path
        script_path = skill_dir / "scripts" / script_name

        if not script_path.exists():
            msg = f"Script not found: {script_name}"
            raise FileNotFoundError(msg)

        result = run_script(
            script_path=script_path,
            args=args or [],
            cwd=self.get_working_dir(),  # session-scoped; state files persist across calls
            timeout=timeout,
            env_extra=env_extra or {},
        )
        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "ok": result.ok,
        }

    def allowed_tools(self, skill_name: str) -> list[str]:
        """Return allowed-tools from cache — no disk read."""
        if self._cache is None:
            self._cache = self._build_cache(self.base_dir)
        entry = self._cache.get(skill_name)
        return entry.metadata.allowed_tools or [] if entry else []
