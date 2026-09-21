#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Inject skill-access / run-skill-script as system tools.

Default: nothing from the skills system is advertised to the LLM.

Implicit:
  - ``spec.skills`` with at least one entry → ``activate_skill`` (and list/read)
  - at least one of those skills has a ``scripts/`` file → ``run_skill_script``

Explicit (manifest):
  - ``{kind: system, name: activate_skill}``
  - ``{kind: system, name: run_skill_script}``
  - ``spec.context_sources: [{native: {auto_inject: true}}]`` (scripts)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mas.library.skills.lib.resolver import resolve_skill_path
from mas.library.skills.plugins.sk_shell import RunSkillScriptPlugin
from mas.library.skills.plugins.sk_tools import SkillToolsPlugin

logger = logging.getLogger(__name__)

SKILL_ACCESS_REFS = frozenset(
    {
        "skills:tools/skill-access.tool.yaml",
        "pkg://skills/tools/skill-access.tool.yaml",
    }
)
SKILL_SHELL_REFS = frozenset(
    {
        "skills:tools/run-skill-script.tool.yaml",
        "pkg://skills/tools/run-skill-script.tool.yaml",
    }
)

_ACTIVATE_NAMES = frozenset({"activate_skill", "skill-access", "skill_access"})
_SCRIPT_NAMES = frozenset({"run_skill_script", "run-skill-script"})


def skill_refs(skills_spec: Any) -> list[str]:
    refs: list[str] = []
    if not isinstance(skills_spec, list):
        return refs
    for item in skills_spec:
        if isinstance(item, str) and item.strip():
            refs.append(item.strip())
    return refs


def _tools_have_ref(tools_spec: list[Any] | None, refs: frozenset[str]) -> bool:
    for item in tools_spec or []:
        if isinstance(item, dict) and str(item.get("ref") or "").strip() in refs:
            return True
    return False


def _explicit_system_tool(tools_spec: list[Any] | None, names: frozenset[str]) -> bool:
    for item in tools_spec or []:
        if not isinstance(item, dict) or item.get("kind") != "system":
            continue
        if str(item.get("name") or "").strip() in names:
            return True
    return False


def any_declared_skill_has_scripts(refs: list[str], *, base_dir: Path) -> bool:
    """True when at least one listed skill has a non-empty ``scripts/`` directory."""
    for ref in refs:
        skill_md = resolve_skill_path(ref, base_dir=base_dir)
        if skill_md is None:
            continue
        scripts = skill_md.parent / "scripts"
        if scripts.is_dir() and any(p.is_file() for p in scripts.iterdir()):
            return True
    return False


def should_inject_activate_skill(
    *,
    skills_spec: Any,
    tools_spec: list[Any] | None,
) -> bool:
    """Advertise activate_skill when skills are listed or explicitly opted in.

    A YAML ``skill-access.tool.yaml`` ref is the older explicit form; skip
    system inject in that case so the plugin is not loaded twice.
    """
    if _tools_have_ref(tools_spec, SKILL_ACCESS_REFS):
        return False
    if skill_refs(skills_spec):
        return True
    return _explicit_system_tool(tools_spec, _ACTIVATE_NAMES)


def should_inject_run_skill_script(
    *,
    skills_spec: Any,
    tools_spec: list[Any] | None,
    base_dir: Path,
    auto_inject_scripts: bool = False,
) -> bool:
    if _tools_have_ref(tools_spec, SKILL_SHELL_REFS):
        return False
    if _explicit_system_tool(tools_spec, _SCRIPT_NAMES) or auto_inject_scripts:
        return True
    refs = skill_refs(skills_spec)
    if not refs:
        return False
    return any_declared_skill_has_scripts(refs, base_dir=base_dir)


def inject_skill_system_tools(
    provider: Any,
    *,
    tools_spec: list[Any] | None,
    skills_spec: Any,
    base_dir: Path,
    auto_inject_scripts: bool = False,
) -> None:
    """Add skill system-tool plugins onto a local tool provider when warranted."""
    add = getattr(provider, "_add_instance", None)
    if not callable(add):
        return

    if should_inject_activate_skill(skills_spec=skills_spec, tools_spec=tools_spec):
        add(SkillToolsPlugin(), None)
        logger.debug("Injected activate_skill system tools")

    if should_inject_run_skill_script(
        skills_spec=skills_spec,
        tools_spec=tools_spec,
        base_dir=base_dir,
        auto_inject_scripts=auto_inject_scripts,
    ):
        add(RunSkillScriptPlugin(), None)
        logger.debug("Injected run_skill_script system tool")
