#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest-scoped working directory — pushd/popd so relative paths match tutorials."""

from __future__ import annotations

import os
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from mas.ctl.env import load_dotenv


@dataclass(frozen=True)
class ManifestSession:
    """Resolved paths after anchoring to the manifest directory."""

    manifest: Path
    manifest_dir: Path
    local_manifest: Path
    overlays: tuple[Path, ...]
    original_cwd: Path


def resolve_manifest(manifest: str | Path, *, cwd: Path | None = None) -> Path:
    """Resolve manifest to an absolute file path (before chdir)."""
    base = cwd or Path.cwd()
    raw = Path(manifest)
    path = raw if raw.is_absolute() else (base / raw).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found: {path}")
    return path


def resolve_overlay_path(path: str | Path, *, orig_cwd: Path, manifest_dir: Path) -> Path:
    """Resolve overlay relative to manifest dir or original cwd."""
    raw = Path(path)
    if raw.is_absolute():
        if not raw.is_file():
            raise FileNotFoundError(f"overlay not found: {raw}")
        return raw
    for base in (manifest_dir, orig_cwd):
        candidate = (base / raw).resolve()
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"overlay not found: {path} (tried {manifest_dir} and {orig_cwd})")


def resolve_path(
    path: str | Path,
    *,
    orig_cwd: Path,
    manifest_dir: Path,
    expect_dir: bool = False,
    create_dir: bool = False,
) -> Path:
    """Resolve a manifest-relative file or directory path."""
    raw = Path(path)
    if raw.is_absolute():
        if expect_dir and not raw.is_dir():
            if create_dir:
                raw.mkdir(parents=True, exist_ok=True)
            elif not raw.exists():
                raise FileNotFoundError(raw)
        elif not expect_dir and not raw.is_file():
            raise FileNotFoundError(raw)
        return raw
    for base in (manifest_dir, orig_cwd):
        candidate = (base / raw).resolve()
        if expect_dir and candidate.is_dir():
            return candidate
        if not expect_dir and candidate.is_file():
            return candidate
    if expect_dir and create_dir:
        target = (manifest_dir / raw).resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target
    if expect_dir:
        candidate = (manifest_dir / raw).resolve()
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"path not found: {path} (tried {manifest_dir} and {orig_cwd})")


def resolve_overlay_paths(
    paths: Sequence[str | Path],
    *,
    orig_cwd: Path,
    manifest_dir: Path,
) -> tuple[Path, ...]:
    return tuple(
        resolve_overlay_path(p, orig_cwd=orig_cwd, manifest_dir=manifest_dir) for p in paths
    )


@contextmanager
def manifest_cwd(
    manifest: str | Path | None,
    *,
    overlay_paths: Sequence[str | Path] = (),
    load_env: bool = True,
) -> Generator[ManifestSession, None, None]:
    """pushd(manifest.parent) for the block; popd on exit.

    Relative overlay paths resolve against manifest dir first, then original cwd.
    """
    orig = Path.cwd()
    if manifest is None:
        yield ManifestSession(
            manifest=Path(),
            manifest_dir=orig,
            local_manifest=Path(),
            overlays=(),
            original_cwd=orig,
        )
        return

    abs_manifest = resolve_manifest(manifest, cwd=orig)
    manifest_dir = abs_manifest.parent
    overlays = resolve_overlay_paths(overlay_paths, orig_cwd=orig, manifest_dir=manifest_dir)

    os.chdir(manifest_dir)
    try:
        if load_env:
            load_dotenv(cwd=orig, manifest_dir=manifest_dir)
        yield ManifestSession(
            manifest=abs_manifest,
            manifest_dir=manifest_dir,
            local_manifest=Path(abs_manifest.name),
            overlays=overlays,
            original_cwd=orig,
        )
    finally:
        os.chdir(orig)
