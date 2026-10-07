#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve one or more metrics.json artefacts in a run folder."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def resolve_metrics_paths(run_dir: Path, spec: Any = "metrics.json") -> list[Path]:
    """Return existing metrics files for *spec* (name, glob, or list of those)."""
    names: list[str]
    if spec is None:
        names = ["metrics.json"]
    elif isinstance(spec, (list, tuple)):
        names = [str(item) for item in spec]
    else:
        names = [str(spec)]
    files: list[Path] = []
    seen: set[Path] = set()
    for name in names:
        if any(ch in name for ch in "*?["):
            matches = sorted(run_dir.glob(name))
        else:
            candidate = run_dir / name
            matches = [candidate] if candidate.exists() else []
        for path in matches:
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            files.append(path)
    return files


def load_merged_session(
    run_dir: Path,
    spec: Any = "metrics.json",
) -> tuple[dict[str, Any], dict[str, Any], list[Path]]:
    """Merge ``session`` maps from one or more metrics files.

    Later files override duplicate metric ids (logged). run_quality lists
    are concatenated. Returns ``(session, run_quality, paths)``.
    """
    paths = resolve_metrics_paths(run_dir, spec)
    session: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []
    status = "ok"
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping %s: %s", path, exc)
            continue
        for metric_id, entry in (doc.get("session") or {}).items():
            if metric_id in session:
                logger.warning(
                    "Duplicate metric id %s in %s; later file wins",
                    metric_id,
                    path.name,
                )
            session[metric_id] = entry
        rq = doc.get("run_quality") or {}
        warnings.extend(rq.get("warnings") or [])
        errors.extend(rq.get("errors") or [])
        if rq.get("status") == "error":
            status = "error"
        elif rq.get("status") == "warn" and status == "ok":
            status = "warn"
    quality = {"warnings": warnings, "errors": errors, "status": status}
    return session, quality, paths


def details_json(entry: dict[str, Any]) -> str:
    details = entry.get("details")
    if details is None:
        return ""
    try:
        return json.dumps(details, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(details)
