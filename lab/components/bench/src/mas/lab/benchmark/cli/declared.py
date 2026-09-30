#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Map on-disk files to artifacts declared in experiment YAML.

The catalog is the ``artifacts:`` maps on the experiment and on each level
(``application``, ``scenario``, ``test``, ``run``).  Files are identified by
those declarations — never by extension or well-known filename.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

import yaml
from mas.lab.lab.config.pipeline import ArtifactSpec

# Directories that are not application / experiment / scenario / test / run
# levels.  ``results/`` and ``plots/`` are leftover dump folders.
_NON_LEVEL_DIRS = frozenset({"results", "plots", "runs", "otel", "traces", ".cache"})
_LEVEL_KEYS = ("run", "test", "scenario", "application")
_ROOT_LEVELS = frozenset({"experiment", "application"})
# User-facing hierarchy.  Top-level ``experiment.artifacts`` occupy the same
# directory as ``application.artifacts``.
DISPLAY_LEVELS = ("application", "scenario", "test", "run")


def display_level(level: str) -> str:
    """Map a catalog level onto the public run/test/scenario/application tree."""
    if level in _ROOT_LEVELS:
        return "application"
    return level


@dataclass(frozen=True)
class ArtifactSlot:
    """One expected artifact at one location, generated or not."""

    name: str
    type: str
    level: str
    location: str
    path: Path
    spec: ArtifactSpec
    generated: bool


@dataclass(frozen=True)
class LocatedArtifact:
    """A declared artifact found on disk."""

    name: str
    type: str
    level: str
    location: str
    path: Path
    spec: ArtifactSpec


def catalog_from_exp_dict(exp: dict[str, Any]) -> list[tuple[str, ArtifactSpec]]:
    """Parse ``(level, spec)`` rows from a loaded experiment mapping."""
    rows: list[tuple[str, ArtifactSpec]] = []
    arts = exp.get("artifacts")
    if isinstance(arts, dict):
        rows.extend(_entries("experiment", arts))
    for level in _LEVEL_KEYS:
        section = exp.get(level)
        if not isinstance(section, dict):
            continue
        level_arts = section.get("artifacts")
        if isinstance(level_arts, dict):
            rows.extend(_entries(level, level_arts))
    return rows


def catalog_from_yaml(yaml_path: Path | str | None) -> list[tuple[str, ArtifactSpec]]:
    """Load the artifact catalog from an experiment YAML path."""
    if not yaml_path:
        return []
    path = Path(yaml_path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    if not isinstance(raw, dict):
        return []
    exp = raw.get("experiment", raw)
    if not isinstance(exp, dict):
        return []
    return catalog_from_exp_dict(exp)


def catalog_from_config(exp: Any) -> list[tuple[str, ArtifactSpec]]:
    """Load the artifact catalog from a parsed experiment config."""
    fn = getattr(exp, "declared_artifacts", None)
    if callable(fn):
        return list(fn())
    return []


def plan_artifacts(
    data_dir: Path,
    catalog: Sequence[tuple[str, ArtifactSpec]],
    *,
    type_filter: str | None = None,
) -> list[ArtifactSlot]:
    """Slots implied by the spec: one per location, marked generated or not.

    Application artifacts always have one slot (the experiment output dir).
    Scenario / test / run artifacts have one slot per directory that exists;
    if none exist yet, a single missing slot still represents the declaration.
    """
    want = type_filter.lower() if type_filter else None
    slots: list[ArtifactSlot] = []
    for level, spec in catalog:
        if want and spec.type.lower() != want:
            continue
        rel = spec.relative_path()
        dirs = list(_iter_level_dirs(data_dir, level))
        if not dirs:
            slots.append(
                ArtifactSlot(
                    name=spec.name,
                    type=spec.type,
                    level=level,
                    location="",
                    path=data_dir / rel,
                    spec=spec,
                    generated=False,
                )
            )
            continue
        for location, directory in dirs:
            path = directory / rel
            slots.append(
                ArtifactSlot(
                    name=spec.name,
                    type=spec.type,
                    level=level,
                    location=location,
                    path=path,
                    spec=spec,
                    generated=path.is_file(),
                )
            )
    return slots


def locate_artifacts(
    data_dir: Path,
    catalog: Sequence[tuple[str, ArtifactSpec]],
    *,
    type_filter: str | None = None,
) -> list[LocatedArtifact]:
    """Resolve declared artifacts to files that exist under *data_dir*."""
    found: list[LocatedArtifact] = []
    for slot in plan_artifacts(data_dir, catalog, type_filter=type_filter):
        if not slot.generated:
            continue
        found.append(
            LocatedArtifact(
                name=slot.name,
                type=slot.type,
                level=slot.level,
                location=slot.location,
                path=slot.path,
                spec=slot.spec,
            )
        )
    return found


def artifact_for_file(
    path: Path,
    catalog: Sequence[tuple[str, ArtifactSpec]],
    data_dir: Path,
) -> LocatedArtifact | None:
    """Return the declared artifact that *path* is, or ``None``."""
    parsed = _level_of(data_dir, path)
    if parsed is None:
        return None
    dir_level, location, level_dir = parsed
    try:
        rel = path.resolve().relative_to(level_dir.resolve())
    except ValueError:
        return None
    match_levels = _ROOT_LEVELS if dir_level == "experiment" else frozenset({dir_level})
    for level, spec in catalog:
        if level not in match_levels:
            continue
        if spec.relative_path() == rel:
            return LocatedArtifact(
                name=spec.name,
                type=spec.type,
                level=level,
                location=location,
                path=path,
                spec=spec,
            )
    return None


def _entries(level: str, arts: dict[str, Any]) -> list[tuple[str, ArtifactSpec]]:
    rows: list[tuple[str, ArtifactSpec]] = []
    for name, value in arts.items():
        try:
            rows.append((level, ArtifactSpec.from_entry(str(name), value)))
        except (ValueError, KeyError, TypeError):
            continue
    return rows


def _iter_level_dirs(data_dir: Path, level: str) -> Iterator[tuple[str, Path]]:
    if level in _ROOT_LEVELS:
        yield "", data_dir
        return
    if not data_dir.is_dir():
        return
    for sc_dir in sorted(data_dir.iterdir()):
        if not _is_level_dir(sc_dir):
            continue
        if level == "scenario":
            yield sc_dir.name, sc_dir
            continue
        for test_dir in sorted(sc_dir.iterdir()):
            if not _is_level_dir(test_dir):
                continue
            test_loc = f"{sc_dir.name}/{test_dir.name}"
            if level == "test":
                yield test_loc, test_dir
                continue
            if level != "run":
                continue
            for run in sorted(test_dir.iterdir()):
                if not run.is_dir() or not run.name.startswith("r"):
                    continue
                yield f"{test_loc}/{run.name}", run


def _is_level_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and not path.name.startswith(".")
        and path.name not in _NON_LEVEL_DIRS
    )


def _level_of(data_dir: Path, path: Path) -> tuple[str, str, Path] | None:
    try:
        rel = path.resolve().relative_to(data_dir.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if not parts or parts[0] in _NON_LEVEL_DIRS:
        return None
    if len(parts) == 1:
        return "experiment", "", data_dir
    sc = parts[0]
    sc_dir = data_dir / sc
    if len(parts) == 2:
        return "scenario", sc, sc_dir
    item = parts[1]
    test_dir = sc_dir / item
    if len(parts) == 3:
        return "test", f"{sc}/{item}", test_dir
    if parts[2].startswith("r"):
        run = parts[2]
        return "run", f"{sc}/{item}/{run}", test_dir / run
    return None
