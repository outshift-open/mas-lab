#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill resolution on realistic app layouts, without git.

Two resolvers must agree: ``lib.resolver.resolve_skill_path`` (fail-fast
missing-skill check and ``run_skill_script`` injection) and
``agentskills.Discovery`` (catalog). A skill the catalog finds but the
fail-fast check rejects aborts agent bootstrap.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from agentskills import Discovery
from mas.library.skills.lib.resolver import resolve_skill_path

from .conftest import make_skill


def _layout(tmp_path: Path) -> dict[str, Path]:
    """library/apps/<app>/v2/agents with skills at several levels, no agents/skills."""
    library = tmp_path / "example-library"
    app = library / "apps" / "example-app"
    agents = app / "v2" / "agents"
    agents.mkdir(parents=True)
    make_skill(library, "library-skill")
    make_skill(app, "app-skill", with_script_py=True)
    make_skill(app / "v2", "version-skill")
    return {"library": library, "app": app, "agents": agents}


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skill resolution must be a pure filesystem operation (no git, no VCS)."""

    def _forbidden(*_a: object, **_k: object) -> None:
        raise AssertionError("skill resolution must not spawn subprocesses")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)


@pytest.mark.parametrize("name", ["library-skill", "app-skill", "version-skill"])
@pytest.mark.parametrize("base", ["agents", "agents/skills"])
def test_resolvers_agree_on_every_ancestor_level(tmp_path: Path, name: str, base: str) -> None:
    paths = _layout(tmp_path)
    base_dir = paths["agents"] / "skills" if base == "agents/skills" else paths["agents"]
    assert not (paths["agents"] / "skills").exists()

    lib_path = resolve_skill_path(name, base_dir=base_dir)
    record = Discovery(manifest_skills=[name], base_dir=base_dir).discover().get(name)

    assert lib_path is not None, f"lib resolver missed {name} from {base}"
    assert record is not None, f"Discovery missed {name} from {base}"
    assert lib_path == record.path


def test_nearest_ancestor_wins_in_both_resolvers(tmp_path: Path) -> None:
    paths = _layout(tmp_path)
    make_skill(paths["app"] / "v2", "library-skill", description="Closer copy.")
    expected = (paths["app"] / "v2" / "skills" / "library-skill" / "SKILL.md").resolve()

    assert resolve_skill_path("library-skill", base_dir=paths["agents"]) == expected
    record = Discovery(manifest_skills=["library-skill"], base_dir=paths["agents"]).discover().get("library-skill")
    assert record is not None and record.path == expected


def test_walk_stops_below_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``~/skills`` is not a skill root; user-level skills live in ``~/.agents/skills``."""
    home = tmp_path / "home"
    make_skill(home, "home-skill")
    agents = home / "repo" / "app" / "agents"
    agents.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert resolve_skill_path("home-skill", base_dir=agents) is None
    assert Discovery(manifest_skills=["home-skill"], base_dir=agents).discover().get("home-skill") is None


def test_user_level_skills_found_from_missing_base_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    make_skill(home, "user-skill", subdir=".agents/skills")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    base_dir = tmp_path / "elsewhere" / "agents" / "skills"

    expected = (home / ".agents" / "skills" / "user-skill" / "SKILL.md").resolve()
    assert resolve_skill_path("user-skill", base_dir=base_dir) == expected
    record = Discovery(manifest_skills=["user-skill"], base_dir=base_dir).discover().get("user-skill")
    assert record is not None and record.path == expected
