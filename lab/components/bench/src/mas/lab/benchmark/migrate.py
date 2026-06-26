#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""Benchmark run migration — move a benchmark output folder to ``~/.mas/labs/``.

This module implements the logic for ``mas-lab benchmark migrate``.

Workflow
--------
1. Validate that ``source_dir`` contains a ``metadata.yaml``.
2. Determine ``target_dir`` (explicit, or auto-derived from the experiment name
   and ``~/.mas/labs/``).
3. Copy the entire directory tree from ``source_dir`` to ``target_dir``.
4. Patch absolute paths in the copied ``metadata.yaml``
   (``run_dir``, ``results_file``, ``plots_dir``).
5. If ``symlink=True`` (default): remove ``source_dir`` and replace it with a
   symlink that points to ``target_dir`` so existing tool invocations that still
   use the old path still work transparently.

The operation is **idempotent** — running it twice is safe because it checks for
an existing symlink at the source location before doing any work.
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mas.lab.benchmark.metadata import BenchmarkMetadata


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass
class MigrateResult:
    """Result of a migrate operation."""

    source: Path
    target: Path
    already_done: bool = False       # source was already a symlink to target
    copied: bool = False
    metadata_patched: bool = False
    symlink_created: bool = False
    dry_run: bool = False

    def summary(self) -> str:
        if self.already_done:
            return f"✓ Already migrated: {self.source}\n  → {self.target}"
        tag = "[dry-run] " if self.dry_run else ""
        lines: list[str] = []
        if self.copied:
            lines.append(f"{tag}✓ Copied    {self.source}")
            lines.append(f"           → {self.target}")
        if self.metadata_patched:
            lines.append(f"{tag}✓ Patched   {self.target / 'metadata.yaml'}")
        if self.symlink_created:
            lines.append(f"{tag}✓ Symlink   {self.source} → {self.target}")
        return "\n".join(lines) if lines else "Nothing to do."


# ---------------------------------------------------------------------------
# Auto-derive target from ~/.mas/labs/ convention
# ---------------------------------------------------------------------------

def default_target(source: Path, root: Path | None = None) -> Path:
    """Propose a canonical ``~/.mas/labs/`` target for *source*.

    Heuristic — reads ``metadata.yaml`` if present and uses ``experiment_name``
    as the leaf.  Falls back to ``source.name``.

    Examples::

        my-lab/output/01-experiment
          → ~/.mas/labs/trip-planner/01-semantic-grouping

        library-samples/apps/trip-planner/experiments/01-exploration/output
          → ~/.mas/labs/trip-planner/01-exploration
    """
    if root is None:
        from mas.lab import paths as _paths
        root = _paths.labs_root()

    meta_path = source / "metadata.yaml"
    if meta_path.exists():
        try:
            meta = BenchmarkMetadata.from_yaml(meta_path)
            # experiment_name is like "01-semantic-grouping" or "trip-planner-01-exploration"
            exp_name = meta.experiment_name.strip()
            return root / exp_name
        except Exception:
            logger.debug('suppressed', exc_info=True)
    # Fallback: use the directory name
    return root / source.name


# ---------------------------------------------------------------------------
# Core migration routine
# ---------------------------------------------------------------------------

def migrate(
    source: Path,
    target: Optional[Path] = None,
    *,
    symlink: bool = True,
    dry_run: bool = False,
    mas_data_root: Optional[Path] = None,
) -> MigrateResult:
    """Migrate *source* benchmark directory to *target*.

    Args:
        source: Existing benchmark run directory (contains ``metadata.yaml``).
        target: Destination directory.  Derived automatically when ``None``.
        symlink: Replace *source* with a symlink after copying.  Defaults to
            ``True`` so legacy relative-path references keep working.
        dry_run: Simulate without touching the filesystem (except reading files).
        mas_data_root: Override for :func:`mas.lab.paths.labs_root` used during auto-derive.

    Returns:
        A :class:`MigrateResult` describing what was (or would be) done.

    Raises:
        FileNotFoundError: If *source* / ``metadata.yaml`` is missing.
        FileExistsError: If *target* already exists and is not a symlink to
            the same location.
    """
    source_raw = Path(source).expanduser()  # keep symlink intact for the check
    source = source_raw.resolve()           # fully resolved for copy / patching

    # ---- already a symlink pointing to target? -------------------------
    if source_raw.is_symlink():
        existing_target = Path(os.readlink(source_raw)).resolve()
        # Only consider "already done" if the target actually looks like a benchmark dir
        if (existing_target / "metadata.yaml").exists():
            if target is None:
                return MigrateResult(source=source_raw, target=existing_target, already_done=True)
            target_resolved = Path(target).expanduser().resolve()
            if existing_target == target_resolved:
                return MigrateResult(source=source_raw, target=target_resolved, already_done=True)

    # ---- validate source -----------------------------------------------
    meta_path = source / "metadata.yaml"
    if not meta_path.exists():
        raise FileNotFoundError(
            f"No metadata.yaml found in {source} — "
            "is this a benchmark run directory?"
        )

    # ---- resolve target ------------------------------------------------
    if target is None:
        target = default_target(source, root=mas_data_root)
    target = Path(target).expanduser().resolve()

    if target == source:
        raise ValueError("source and target are the same directory")

    result = MigrateResult(source=source_raw, target=target, dry_run=dry_run)

    # ---- copy ----------------------------------------------------------
    if target.exists():
        if not dry_run:
            raise FileExistsError(
                f"Target already exists: {target}\n"
                "Remove it first or choose a different target."
            )
    else:
        if not dry_run:
            shutil.copytree(source, target)
        result.copied = True

    # ---- patch metadata.yaml ------------------------------------------
    copied_meta = target / "metadata.yaml"
    if not dry_run and copied_meta.exists():
        _patch_metadata(copied_meta, old_root=str(source), new_root=str(target))
    result.metadata_patched = True

    # ---- symlink -------------------------------------------------------
    if symlink:
        if not dry_run:
            # Remove source cleanly: unlink if it's a symlink, rmtree if a dir
            if source_raw.is_symlink():
                source_raw.unlink()
            else:
                shutil.rmtree(source_raw)
            os.symlink(target, source_raw)
        result.symlink_created = True

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _patch_metadata(meta_path: Path, old_root: str, new_root: str) -> None:
    """Replace all occurrences of *old_root* with *new_root* in *meta_path*."""
    text = meta_path.read_text()
    text = text.replace(old_root, new_root)
    meta_path.write_text(text)
