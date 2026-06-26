#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Load .env for ctl CLI and lab runs."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(
    *,
    cwd: Path | None = None,
    manifest_dir: Path | None = None,
    explicit: Path | None = None,
    override: bool = False,
) -> Path | None:
    """Load dotenv from explicit path, CWD, manifest directory, and repo ancestors."""
    try:
        from dotenv import load_dotenv as _load
    except ImportError:
        return None

    seen: set[Path] = set()
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    base = cwd or Path.cwd()
    candidates.append(base / ".env")
    if manifest_dir:
        candidates.append(manifest_dir / ".env")
        for parent in [manifest_dir, *manifest_dir.parents]:
            if (parent / ".git").exists() or parent == parent.parent:
                candidates.append(parent / ".env")
                break

    loaded: Path | None = None
    for path in candidates:
        resolved = path.resolve()
        if not resolved.is_file() or resolved in seen:
            continue
        seen.add(resolved)
        _load(resolved, override=override)
        loaded = resolved

    if loaded is not None:
        os.environ.setdefault("MAS_DOTENV_LOADED", str(loaded))
    return loaded
