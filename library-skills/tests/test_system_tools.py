#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill system-tool injection: implicit from spec.skills / scripts, explicit in manifest."""

from __future__ import annotations

from pathlib import Path

from mas.library.skills.plugins.system_tools import (
    should_inject_activate_skill,
    should_inject_run_skill_script,
)


def _skill(tmp_path: Path, name: str, *, scripts: bool = False) -> None:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Use when testing. Call activate_skill.\n---\n# {name}\n",
        encoding="utf-8",
    )
    if scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")


def test_activate_skill_not_injected_without_skills() -> None:
    assert should_inject_activate_skill(skills_spec=[], tools_spec=[]) is False
    assert should_inject_activate_skill(skills_spec=None, tools_spec=None) is False


def test_activate_skill_implicit_when_skills_listed() -> None:
    assert should_inject_activate_skill(skills_spec=["answer-formatting"], tools_spec=[]) is True


def test_activate_skill_explicit_kind_system() -> None:
    tools = [{"kind": "system", "name": "activate_skill"}]
    assert should_inject_activate_skill(skills_spec=[], tools_spec=tools) is True


def test_activate_skill_skipped_when_yaml_ref_present() -> None:
    tools = [{"ref": "skills:tools/skill-access.tool.yaml"}]
    assert should_inject_activate_skill(skills_spec=["answer-formatting"], tools_spec=tools) is False


def test_run_skill_script_not_injected_without_scripts(tmp_path: Path) -> None:
    _skill(tmp_path, "plain")
    assert (
        should_inject_run_skill_script(
            skills_spec=["plain"],
            tools_spec=[],
            base_dir=tmp_path,
        )
        is False
    )


def test_run_skill_script_implicit_when_skill_has_scripts(tmp_path: Path) -> None:
    _skill(tmp_path, "with-scripts", scripts=True)
    assert (
        should_inject_run_skill_script(
            skills_spec=["with-scripts"],
            tools_spec=[],
            base_dir=tmp_path,
        )
        is True
    )


def test_run_skill_script_explicit_kind_system(tmp_path: Path) -> None:
    _skill(tmp_path, "plain")
    tools = [{"kind": "system", "name": "run_skill_script"}]
    assert (
        should_inject_run_skill_script(
            skills_spec=["plain"],
            tools_spec=tools,
            base_dir=tmp_path,
        )
        is True
    )


def test_run_skill_script_auto_inject_flag(tmp_path: Path) -> None:
    _skill(tmp_path, "plain")
    assert (
        should_inject_run_skill_script(
            skills_spec=["plain"],
            tools_spec=[],
            base_dir=tmp_path,
            auto_inject_scripts=True,
        )
        is True
    )
