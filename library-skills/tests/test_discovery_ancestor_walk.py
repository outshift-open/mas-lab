#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ancestor-dir walk-up must reach the git root's own skills/ dir.

Regression coverage for the monorepo-shared-skills gap: the walk used to stop
exactly at the git root boundary, before checking that directory's own
`skills/` subfolder, so a root-level `<repo>/skills/` was never found from an
app nested a few levels below it. See docs/spec-coverage.md.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agentskills import Discovery

from .conftest import make_skill


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def test_walk_up_finds_git_root_skills_dir(tmp_path: Path):
    """A skill living only in <git_root>/skills/ is discoverable from a
    nested app dir that has no local skills/ of its own."""
    _git_init(tmp_path)
    make_skill(tmp_path, "root-skill", description="Lives at the repo root.")

    app_dir = tmp_path / "mas-lab" / "apps" / "sre-triage"
    app_dir.mkdir(parents=True)

    discovery = Discovery(manifest_skills=["root-skill"], base_dir=app_dir)
    registry = discovery.discover()

    rec = registry.get("root-skill")
    assert rec is not None
    assert rec.path == (tmp_path / "skills" / "root-skill" / "SKILL.md").resolve()


def test_local_skills_dir_still_shadows_root(tmp_path: Path):
    """An app-local skills/<name> still wins over the same name at git root
    (first-found-wins is unaffected by including the root in the walk)."""
    _git_init(tmp_path)
    make_skill(tmp_path, "dup", description="Root version.")

    app_dir = tmp_path / "app"
    make_skill(app_dir, "dup", description="Local version.")

    discovery = Discovery(manifest_skills=["dup"], base_dir=app_dir)
    registry = discovery.discover()

    rec = registry.get("dup")
    assert rec is not None
    assert rec.path == (app_dir / "skills" / "dup" / "SKILL.md").resolve()


def test_ancestor_walk_depth_limit_can_still_exclude_git_root(tmp_path: Path):
    """ancestor_walk_depth=0 stops before reaching a git root several levels
    up, preserving the escape hatch for callers that don't want monorepo
    sharing."""
    _git_init(tmp_path)
    make_skill(tmp_path, "root-skill", description="Lives at the repo root.")

    app_dir = tmp_path / "mas-lab" / "apps" / "sre-triage"
    app_dir.mkdir(parents=True)

    discovery = Discovery(
        manifest_skills=["root-skill"], base_dir=app_dir, ancestor_walk_depth=0
    )
    registry = discovery.discover()

    assert registry.get("root-skill") is None
