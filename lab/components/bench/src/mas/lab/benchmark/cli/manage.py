#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark metadata and migration commands."""

import logging
from pathlib import Path

from mas.lab.benchmark.run_manager import BenchmarkRunManager

from mas.lab.benchmark.cli.common import _resolve_run_manager_dir

logger = logging.getLogger(__name__)


def update_command(args) -> int:
    """Update benchmark metadata (name, tags)."""
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )
    
    # Collect updates
    name = getattr(args, "name", None)
    tags = None
    add_tags = None
    remove_tags = None
    
    # Parse tags operations
    if hasattr(args, "tags") and args.tags:
        tags = [t.strip() for t in args.tags.split(",")]
    
    if hasattr(args, "add_tag") and args.add_tag:
        add_tags = [args.add_tag]
    
    if hasattr(args, "remove_tag") and args.remove_tag:
        remove_tags = [args.remove_tag]
    
    # Check if any update requested
    if not any([name, tags, add_tags, remove_tags]):
        logger.error("No updates specified. Use --name, --tags, --add-tag, or --remove-tag")
        return 1
    
    # Update
    success = run_manager.update_metadata(
        benchmark_id=args.benchmark_id,
        name=name,
        tags=tags,
        add_tags=add_tags,
        remove_tags=remove_tags,
    )
    
    if not success:
        return 1
    
    # Show updated info
    result = run_manager.get_run(args.benchmark_id)
    if result:
        metadata, run_dir = result
        print(f"\n✓ Updated benchmark: {metadata.short_id}")
        if metadata.name:
            print(f"  Name: {metadata.name}")
        if metadata.tags:
            print(f"  Tags: {', '.join(metadata.tags)}")
    
    return 0


def rename_command(args) -> int:
    """Rename a benchmark run directory to a new slug.

    Performs an atomic directory rename (same filesystem, no data copy) and
    patches the absolute path fields in ``metadata.yaml`` so they reflect the
    new location.  Supports ``--dry-run`` to preview the operation without
    touching the filesystem.
    """
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )

    result = run_manager.get_run(args.benchmark_id)
    if not result:
        logger.error(f"Benchmark not found: {args.benchmark_id}")
        return 1

    metadata, old_run_dir = result
    new_slug = args.new_slug.strip()

    if not new_slug:
        logger.error("new_slug must not be empty")
        return 1

    new_run_dir = old_run_dir.parent / new_slug

    if old_run_dir == new_run_dir:
        print(f"Directory is already named '{new_slug}' — nothing to do.")
        return 0

    if new_run_dir.exists():
        logger.error(f"Target directory already exists: {new_run_dir}")
        return 1

    print(f"  {old_run_dir}")
    print(f"→ {new_run_dir}")

    if getattr(args, "dry_run", False):
        print()
        print("[dry-run — no files were modified]")
        return 0

    # Atomic rename (same filesystem only, no data copy)
    old_run_dir.rename(new_run_dir)

    # Patch absolute path fields in metadata
    old_prefix = str(old_run_dir)
    new_prefix = str(new_run_dir)

    def _repatch(value: str) -> str:
        if value and value.startswith(old_prefix):
            return new_prefix + value[len(old_prefix):]
        return value

    metadata.run_dir = _repatch(metadata.run_dir)
    metadata.results_file = _repatch(metadata.results_file)
    metadata.plots_dir = _repatch(metadata.plots_dir)

    run_manager.save_metadata(new_run_dir, metadata)

    print()
    print(f"✓ Renamed benchmark {metadata.short_id}")

    return 0


def migrate_command(args) -> int:
    """Migrate a benchmark run directory to :func:`mas.lab.paths.labs_root` (or another root).

    Copies the data, patches absolute paths in metadata.yaml, and
    optionally replaces the old directory with a symlink so existing
    references keep working.
    """
    from mas.lab.benchmark.migrate import migrate, default_target

    source = Path(args.source_dir).expanduser()          # do NOT resolve — preserve symlink for already-done detection
    target = Path(args.target_dir).expanduser() if getattr(args, "target_dir", None) else None
    symlink = not getattr(args, "no_symlink", False)
    dry_run = getattr(args, "dry_run", False)
    mas_data_root = Path(args.mas_data_root).expanduser() if getattr(args, "mas_data_root", None) else None

    if dry_run:
        print("  [dry-run — no files will be modified]\n")

    try:
        result = migrate(
            source=source,
            target=target,
            symlink=symlink,
            dry_run=dry_run,
            mas_data_root=mas_data_root,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    print(result.summary())

    if not dry_run and not result.already_done:
        print()
        print("Tip: update experiment.yaml output_dir to point to the new location:")
        print(f"  output_dir: {result.target}")

    return 0


