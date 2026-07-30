#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark export/import commands."""

import logging
from pathlib import Path

from mas.lab.benchmark.run_manager import BenchmarkRunManager

from mas.lab.benchmark.cli.common import _get_trace_cache_dir, _resolve_run_manager_dir

logger = logging.getLogger(__name__)

def export_command(args) -> int:
    """Pack a benchmark run into a portable .tar.gz archive.

    The archive layout::

        <benchmark_id>/                    ← benchmark output dir
            metadata.yaml
            results.csv
            plots/
            <scenario>/item<n>/r<n>/
                traces/events.jsonl
                traces/otel_spans.jsonl    (if present)
                ...
        trace-cache/                       ← referenced trace-cache entries
            <run_hash>/
                events.jsonl
                run_info.json
                ...
        MANIFEST.json                      ← import metadata
    """
    import json as _json
    import tarfile
    import tempfile

    benchmark_id = args.benchmark_id
    include_trace_cache = getattr(args, "include_trace_cache", True)
    dry_run = getattr(args, "dry_run", False)

    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )

    # Handle "last" / "latest" as alias for most-recent run
    result = None
    if benchmark_id in ("last", "latest"):
        result = run_manager.get_last_run()
        if not result:
            logger.error("No benchmark runs found.")
            return 1
        benchmark_id = result[0].benchmark_id

    if result is None:
        result = run_manager.get_run(benchmark_id)
        if not result:
            # Fallback: match by experiment_name
            for run_info in run_manager.list_runs():
                if run_info.experiment_name == benchmark_id:
                    result = run_manager.get_run(run_info.benchmark_id)
                    break
    if not result:
        logger.error("Benchmark not found: %s", benchmark_id)
        return 1

    metadata, run_dir = result
    run_dir = run_dir.resolve()

    # Determine output path
    out_path = getattr(args, "output", None)
    if out_path is None:
        out_path = Path.cwd() / f"{metadata.short_id}.tar.gz"
    out_path = Path(out_path).expanduser().resolve()

    print(f"\nExporting benchmark {metadata.short_id} → {out_path}")
    print(f"  Run dir:  {run_dir}")

    # Collect trace-cache entries referenced in results.csv / metadata
    trace_dirs: list[Path] = []
    if include_trace_cache:
        explicit_tc = getattr(args, "trace_cache_dir", None)
        tc_root = _get_trace_cache_dir(explicit=explicit_tc)
        results_csv = run_dir / "results.csv"
        if results_csv.exists():
            import csv as _csv
            with open(results_csv) as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    trace_path_str = row.get("trace_path", "")
                    if trace_path_str:
                        tp = Path(trace_path_str)
                        # tc_entry = the direct child of tc_root that holds this trace
                        # e.g. tc_root/<hash>/traces/events.jsonl → tc_root/<hash>
                        try:
                            tc_entry = tc_root / Path(trace_path_str).relative_to(tc_root).parts[0]
                        except (ValueError, IndexError):
                            # Fallback: walk up until a direct child of tc_root
                            tc_entry = tp.parent
                            while tc_entry.parent != tc_root and tc_entry.parent != tc_entry:
                                tc_entry = tc_entry.parent
                        if tc_entry.exists() and tc_entry.parent == tc_root:
                            trace_dirs.append(tc_entry.resolve())
        trace_dirs = list({str(d): d for d in trace_dirs}.values())  # deduplicate
        print(f"  Trace-cache entries: {len(trace_dirs)}")

    # Count total run_info.json entries in the benchmark dir (= expected run count)
    total_runs = sum(1 for _ in run_dir.rglob("run_info.json"))

    # Build MANIFEST
    manifest = {
        "benchmark_id": metadata.benchmark_id,
        "short_id": metadata.short_id,
        "experiment_name": metadata.experiment_name,
        "run_dir_basename": run_dir.name,
        "has_trace_cache": bool(trace_dirs),
        "total_runs": total_runs,
        "trace_cache_entry_names": [d.name for d in trace_dirs],
    }

    if dry_run:
        print("\n  [dry-run — nothing written]")
        print(f"  Would create: {out_path}")
        print(f"  Benchmark dir: {run_dir}")
        for td in trace_dirs:
            print(f"  Trace-cache:  {td}")
        return 0

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as mf:
        _json.dump(manifest, mf, indent=2)
        manifest_path = Path(mf.name)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out_path, "w:gz") as tar:
            # Add MANIFEST.json at archive root
            tar.add(manifest_path, arcname="MANIFEST.json")
            # Add benchmark run dir
            tar.add(run_dir, arcname=run_dir.name)
            # Add trace-cache entries
            for tc_dir in trace_dirs:
                tar.add(tc_dir, arcname=f"trace-cache/{tc_dir.name}")
    finally:
        manifest_path.unlink(missing_ok=True)

    size_mb = out_path.stat().st_size / 1_048_576
    print(f"\n✓ Exported {size_mb:.1f} MB → {out_path}")
    print(f"\nTo restore:\n  mas-lab benchmark import {out_path}")
    print(f"\nTo restore to a temp directory:\n  mas-lab benchmark import {out_path} \\")
    print(f"      --output-dir /tmp/test-bench --trace-cache /tmp/test-trace-cache")
    return 0


def import_command(args) -> int:
    """Restore a benchmark archive produced by ``benchmark export``."""
    import json as _json
    import tarfile

    tarball = Path(args.tarball).expanduser().resolve()
    dry_run = getattr(args, "dry_run", False)

    if not tarball.exists():
        logger.error("Archive not found: %s", tarball)
        return 1

    # Peek at MANIFEST.json inside the archive
    with tarfile.open(tarball, "r:gz") as tar:
        try:
            mf_member = tar.getmember("MANIFEST.json")
        except KeyError:
            logger.error("Archive is missing MANIFEST.json — was it created by 'benchmark export'?")
            return 1
        manifest = _json.loads(tar.extractfile(mf_member).read())

    short_id = manifest["short_id"]
    run_dir_basename = manifest["run_dir_basename"]
    has_trace_cache = manifest.get("has_trace_cache", False)
    total_runs = manifest.get("total_runs", len(manifest.get("trace_cache_entry_names", [])))
    tc_entry_names: list[str] = manifest.get("trace_cache_entry_names", [])

    # Resolve target directories
    output_dir_arg = getattr(args, "output_dir", None)
    trace_cache_arg = getattr(args, "trace_cache_dir", None)

    if output_dir_arg:
        bench_target = Path(output_dir_arg).expanduser().resolve()
    else:
        from mas.lab import paths as _paths
        bench_target = (_paths.benchmark_root() / run_dir_basename).resolve()

    trace_cache_target = _get_trace_cache_dir(explicit=trace_cache_arg)

    # Determine the data root for the demo hint
    from mas.lab import paths as _paths
    data_root = _paths.data_root()

    # Count cached entries BEFORE import
    cached_before = sum(1 for name in tc_entry_names if (trace_cache_target / name).exists())

    print(f"\nImporting benchmark {short_id} from {tarball.name}")
    print(f"  Benchmark dir:  {bench_target}")
    if has_trace_cache:
        print(f"  Trace-cache:    {trace_cache_target}")
    print()
    print(f"  Before import — cache coverage: {cached_before}/{total_runs} runs available")
    if cached_before == 0 and total_runs > 0:
        print(f"  (to verify from a fresh environment, run first:)")
        print(f"    export {_paths.MAS_DATA_ROOT_ENV}={data_root}")
        print(f"    mas-lab benchmark show {short_id}")
    print()

    if dry_run:
        with tarfile.open(tarball, "r:gz") as tar:
            members = [m.name for m in tar.getmembers() if not m.name.endswith(".json") or m.name == "MANIFEST.json"]
            print(f"  [dry-run — nothing written]")
            print(f"  Archive contains {len(members)} entries")
        return 0

    bench_target.mkdir(parents=True, exist_ok=True)
    trace_cache_target.mkdir(parents=True, exist_ok=True)

    # Extract archive, routing entries to correct destinations
    with tarfile.open(tarball, "r:gz") as tar:
        # Build a quick lookup for trace-cache member names (for hardlink resolution)
        tc_members_in_archive: set[str] = {
            m.name for m in tar.getmembers() if m.name.startswith("trace-cache/")
        }
        for member in tar.getmembers():
            name = member.name
            if name == "MANIFEST.json":
                continue
            if name.startswith("trace-cache/"):
                rel = name[len("trace-cache/"):]
                dest = trace_cache_target / rel
            elif name.startswith(run_dir_basename + "/") or name == run_dir_basename:
                rel = name[len(run_dir_basename):].lstrip("/")
                dest = bench_target / rel if rel else bench_target
            else:
                # Unexpected entry — skip
                continue

            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif member.islnk() or member.issym():
                # The run_dir may contain hardlinks/symlinks pointing to trace-cache
                # entries on the original machine. Rewrite them to the new trace-cache
                # location or extract the referenced content from the archive.
                linkname = member.linkname
                # Strip the run_dir_basename prefix if present (tar hardlink format)
                if linkname.startswith(run_dir_basename + "/"):
                    abs_part = linkname[len(run_dir_basename) + 1:]
                else:
                    abs_part = linkname
                # Find "trace-cache/<hash>/<file>" suffix in the link target
                tc_marker = "trace-cache/"
                idx = abs_part.rfind(tc_marker)
                if idx >= 0:
                    tc_rel = abs_part[idx + len(tc_marker):]  # e.g. "HASH/events.jsonl"
                    archive_tc_name = f"trace-cache/{tc_rel}"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if archive_tc_name in tc_members_in_archive:
                        # Copy content from the archived trace-cache entry
                        # Unlink dangling symlinks first (e.g. after trace-cache wipe)
                        if dest.is_symlink():
                            dest.unlink()
                        fobj = tar.extractfile(archive_tc_name)
                        if fobj is not None:
                            dest.write_bytes(fobj.read())
                    else:
                        # Rewrite as symlink to new trace-cache location
                        new_target = str(trace_cache_target / tc_rel)
                        if dest.is_symlink() or dest.exists():
                            dest.unlink(missing_ok=True)
                        dest.symlink_to(new_target)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                fobj = tar.extractfile(member)
                if fobj is not None:
                    dest.write_bytes(fobj.read())

    # Patch absolute paths in metadata.yaml
    meta_path = bench_target / "metadata.yaml"
    if meta_path.exists():
        import yaml as _yaml
        raw = _yaml.safe_load(meta_path.read_text()) or {}
        old_run_dir = raw.get("run_dir", "")
        if old_run_dir and old_run_dir != str(bench_target):
            old_prefix = old_run_dir.rstrip("/")
            new_prefix = str(bench_target).rstrip("/")
            def _repatch(v: str) -> str:
                if v and v.startswith(old_prefix):
                    return new_prefix + v[len(old_prefix):]
                return v
            for field in ("run_dir", "results_file", "plots_dir", "experiment_yaml_path"):
                if field in raw:
                    raw[field] = _repatch(raw[field])
            meta_path.write_text(_yaml.dump(raw, default_flow_style=False))
            logger.debug("Patched metadata.yaml: %s → %s", old_prefix, new_prefix)

    # Count cached entries AFTER import
    cached_after = sum(1 for name in tc_entry_names if (trace_cache_target / name).exists())

    print(f"✓ Imported benchmark {short_id} → {bench_target}")
    print(f"  After import  — cache coverage: {cached_after}/{total_runs} runs available")
    print()
    print(f"  mas-lab benchmark show {short_id}")
    return 0


