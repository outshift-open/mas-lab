#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""Resolve lab / experiment targets for golden-run capture."""

from pathlib import Path
from typing import Iterable

from mas.runtime.spec.source import load_yaml_file

DEFAULT_MANIFEST = Path("tests/fixtures/golden-runs/labs.yaml")


def load_labs_manifest(manifest_path: Path, *, root: Path) -> dict[str, Path]:
    """Load manifest ``labs: [{label, experiment}, ...]`` → label → experiment path."""
    if not manifest_path.is_file():
        return {}
    data = load_yaml_file(manifest_path)
    entries = data.get("labs") or data.get("paper_labs") or []
    out: dict[str, Path] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        exp_raw = entry.get("experiment")
        if not label or not exp_raw:
            continue
        out[label] = (root / str(exp_raw)).resolve()
    return out


def find_experiment_yaml(lab_path: Path) -> Path | None:
    """Locate an experiment YAML under a lab directory."""
    if lab_path.is_file():
        if lab_path.suffix.lower() in {".yaml", ".yml"}:
            return lab_path.resolve()
        return None
    if not lab_path.is_dir():
        return None

    root_candidate = lab_path / "experiment.yaml"
    if root_candidate.is_file():
        return root_candidate.resolve()

    nested = sorted(lab_path.glob("**/experiment.yaml"))
    if nested:
        return nested[0].resolve()
    return None


def default_label_for(path: Path, *, root: Path) -> str:
    """Derive a stable golden fixture label from an experiment path."""
    rel = path.resolve()
    try:
        rel = rel.relative_to(root)
    except ValueError:
        logger.debug('suppressed', exc_info=True)
    parts = list(rel.parts)
    if parts and parts[-1] in ("experiment.yaml", "experiment.yml"):
        parts = parts[:-1]
    if parts and parts[-1].endswith(".lab"):
        return parts[-1].removesuffix(".lab")
    return "-".join(parts) if parts else path.stem


def resolve_lab_spec(
    spec: str,
    *,
    root: Path,
    manifest: dict[str, Path],
) -> tuple[str, Path]:
    """Resolve one ``--labs`` value to ``(label, experiment_path)``."""
    raw = spec.strip()
    if not raw:
        raise ValueError("empty --labs value")

    if raw in manifest:
        exp = manifest[raw]
        return raw, exp

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()

    if candidate.is_file():
        label = next((k for k, v in manifest.items() if v == candidate), "")
        if not label:
            label = default_label_for(candidate, root=root)
        return label, candidate

    exp = find_experiment_yaml(candidate)
    if exp is not None:
        label = next((k for k, v in manifest.items() if v == exp), "")
        if not label:
            label = default_label_for(exp, root=root)
        return label, exp

    raise FileNotFoundError(
        f"could not resolve lab target {spec!r} "
        f"(not in manifest, not a file, no experiment.yaml under {candidate})"
    )


def resolve_lab_targets(
    specs: Iterable[str],
    *,
    root: Path,
    manifest_path: Path,
    all_from_manifest: bool = False,
) -> list[tuple[str, Path]]:
    """Expand ``--labs`` values (and optional manifest ``all``) to capture targets."""
    manifest = load_labs_manifest(manifest_path, root=root)
    if all_from_manifest or any(s.strip().lower() == "all" for s in specs):
        return sorted(manifest.items(), key=lambda x: x[0])

    targets: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for spec in specs:
        if spec.strip().lower() == "all":
            continue
        label, exp = resolve_lab_spec(spec, root=root, manifest=manifest)
        if label in seen:
            continue
        seen.add(label)
        targets.append((label, exp))
    return targets
