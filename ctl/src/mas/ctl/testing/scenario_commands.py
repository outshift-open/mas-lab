#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Replay mas-lab tutorial scenario YAML commands against v2 CLIs."""

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import yaml

_ONLINE_MODE: bool = os.environ.get("TUTORIAL_ONLINE", "").strip().lower() in ("1", "true", "yes")

# v2 CLI mapping: mas-ctl owns validate + chat (replaces mas-runtime run-agent).
_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\bmas-runtime validate\b", "mas-ctl validate"),
    (r"\bmas-runtime run-agent\b", "mas-ctl chat"),
)


class CommandCase(NamedTuple):
    scenario_id: str
    section_title: str
    step_title: str
    command: str
    working_dir: Path
    expected_exit_code: int
    expected_output: str
    requires: tuple[str, ...] = ()
    allowed_modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioRef:
    yaml_path: Path
    working_dir: Path
    scenario_id: str


def default_scenarios(lab_root: Path) -> list[ScenarioRef]:
    """Tutorial scenario YAMLs in mas-lab (reuse mas-lab as spec source)."""
    return [
        ScenarioRef(
            lab_root / "docs/tutorials/00-environment-setup/demo/scenario.yaml",
            lab_root,
            "tuto-00",
        ),
        ScenarioRef(
            lab_root / "docs/tutorials/01-building-an-agent/demo/scenario.yaml",
            lab_root,
            "tuto-01",
        ),
        ScenarioRef(
            lab_root / "docs/tutorials/02-creating-a-mas/demo/scenario.yaml",
            lab_root,
            "tuto-02",
        ),
        ScenarioRef(
            lab_root / "docs/tutorials/03-experiments-and-analysis/demo/scenario.yaml",
            lab_root,
            "tuto-03",
        ),
    ]


def rewrite_command_for_v2(command: str) -> str:
    cmd = " ".join(command.split())
    for pattern, repl in _REWRITES:
        cmd = re.sub(pattern, repl, cmd)
    if "mas-ctl" in cmd:
        cmd = re.sub(r"--overlay\b", "-o", cmd)
    return _hoist_mas_ctl_global_flags(cmd)


def _hoist_mas_ctl_global_flags(command: str) -> str:
    """Move ``-v`` before the mas-ctl subcommand (global Click option)."""
    m = re.match(r"mas-ctl\s+(chat|validate|run-mas|compose|plan)(\s+.*)?$", command)
    if not m:
        return command
    sub, rest = m.group(1), m.group(2) or ""
    flags: list[str] = []
    while True:
        vm = re.search(r"(?:^|\s)(-v)\b", rest)
        if not vm:
            break
        flags.append("-v")
        rest = (rest[: vm.start()] + rest[vm.end() :]).strip()
    if not flags:
        return command
    prefix = " ".join(flags)
    return f"mas-ctl {prefix} {sub} {rest}".strip()


def _step_runnable(step: dict) -> bool:
    modes = step.get("allowed_modes")
    if not modes:
        return True
    if "offline" in modes:
        return True
    return _ONLINE_MODE


def collect_command_cases(scenarios: list[ScenarioRef]) -> list[CommandCase]:
    cases: list[CommandCase] = []
    for ref in scenarios:
        if not ref.yaml_path.is_file():
            continue
        raw = yaml.safe_load(ref.yaml_path.read_text(encoding="utf-8"))
        working_dir_str = raw.get("working_dir", ".")
        working_dir = (ref.working_dir / working_dir_str).resolve()
        for section in raw.get("sections", []):
            sec_title = section.get("title", section.get("id", "?"))
            for step in section.get("steps", []):
                if step.get("type") != "command":
                    continue
                if not _step_runnable(step):
                    continue
                cases.append(
                    CommandCase(
                        scenario_id=ref.scenario_id,
                        section_title=sec_title,
                        step_title=step.get("title", step.get("command", "?")[:40]),
                        command=rewrite_command_for_v2(step["command"]),
                        working_dir=working_dir,
                        expected_exit_code=step.get("expected_exit_code", 0),
                        expected_output=step.get("expected_output", ""),
                        requires=tuple(step.get("requires", [])),
                        allowed_modes=tuple(step.get("allowed_modes", [])),
                    )
                )
    return cases


def requires_available(requires: tuple[str, ...]) -> str | None:
    for mod in requires:
        if importlib.util.find_spec(mod) is None:
            return mod
    return None


def mas_lab_runnable(lab_root: Path) -> str | None:
    """Return skip reason when mas-lab CLI cannot run in this checkout."""
    if not lab_root.is_dir():
        return "MAS_LAB_ROOT not found"
    import subprocess
    import sys

    if not (lab_root / "pyproject.toml").is_file():
        return "mas-lab pyproject.toml missing"
    try:
        r = subprocess.run(
            ["uv", "run", "--directory", str(lab_root), "mas-lab", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:
        return f"mas-lab health check failed: {exc}"
    if r.returncode != 0:
        return "mas-lab not runnable in current checkout"
    return None
