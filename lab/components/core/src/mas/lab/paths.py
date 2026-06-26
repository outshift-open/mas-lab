#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Canonical data path resolution for mas-lab.

All persistent data lives under a single *data root* directory, defaulting
to ``~/.mas-lab``.  Two first-level subdirectories structure the contents:

``~/.mas-lab/labs/``
    All experiment outputs — whether from a named lab (``*.lab/``) or a
    standalone benchmark run.  A *lab* is a coherent set of experiments; an
    *experiment* is a reproducible result (like a row in a paper table).
    Benchmarks are simply the tool used to execute experiments within a lab.

    Hierarchy::

        ~/.mas-lab/labs/
            <lab-name>/            ← one directory per lab
                <experiment-name>/ ← one directory per experiment
                    <scenario>[.vN]/
                        item<N>/
                            r<N>/  ← individual run artefacts

``~/.mas-lab/data/``
    Ephemeral / support data: trace cache, standalone run records, logs,
    pipeline scratch outputs.  Rarely needs manual inspection.

Each sub-tree can be overridden independently via environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path

# -----------------------------------------------------------------
# Environment-variable names (public — used by `mas-lab config`)
# -----------------------------------------------------------------
MAS_DATA_ROOT_ENV           = "MAS_DATA_ROOT"
MAS_LABS_ROOT_ENV           = "MAS_LABS_ROOT"
MAS_LAB_DATA_ENV            = "MAS_LAB_DATA"        # ~/.mas-lab/data override
MAS_TRACE_CACHE_ENV         = "MAS_TRACE_CACHE"
MAS_DATA_CACHE_ENV          = "MAS_DATA_CACHE"
MAS_RUNS_ROOT_ENV           = "MAS_RUNS_ROOT"
MAS_STANDALONE_RUNS_ENV     = "MAS_STANDALONE_RUNS_ROOT"


# -----------------------------------------------------------------
# Path resolvers
# -----------------------------------------------------------------

def _load_mas_config_yaml() -> dict:
    """Load ``~/.mas/config.yaml`` when the runtime user-config module is unavailable."""
    cfg_path = Path.home() / ".mas" / "config.yaml"
    if not cfg_path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _user_config_paths() -> tuple[Path | None, Path | None, Path | None]:
    """Return (labs_dir, cache_dir, runs_dir) from ``~/.mas/config.yaml`` if loaded."""
    try:
        from mas.runtime.user_config import get_user_config

        cfg = get_user_config()
        if getattr(cfg, "_config_exists", False):
            return cfg.labs_dir, cfg.cache_dir, cfg.runs_dir
    except Exception:
        pass

    raw = _load_mas_config_yaml()
    if not raw:
        return None, None, None

    def _as_path(key: str) -> Path | None:
        value = raw.get(key)
        if not value:
            return None
        return Path(str(value)).expanduser()

    return _as_path("labs_dir"), _as_path("cache_dir"), _as_path("runs_dir")


def data_root() -> Path:
    """Return the root directory for all mas-lab persistent data.

    Resolved from ``$MAS_DATA_ROOT``; else parent of ``labs_dir`` from
    ``~/.mas/config.yaml`` when configured; else ``~/.mas-lab``.
    """
    _raw = os.environ.get(MAS_DATA_ROOT_ENV, "").strip()
    if _raw:
        return Path(_raw).expanduser()
    _labs, _cache, _runs = _user_config_paths()
    if _labs is not None:
        # labs_dir is typically ~/.mas/labs → data root ~/.mas
        return _labs.parent
    return Path.home() / ".mas-lab"


def labs_root() -> Path:
    """Return the root directory for all experiment outputs (labs + benchmarks).

    Resolved from ``$MAS_LABS_ROOT``; else ``labs_dir`` from ``~/.mas/config.yaml``;
    else ``<data_root>/labs``.
    """
    _raw = os.environ.get(MAS_LABS_ROOT_ENV, "").strip()
    if _raw:
        return Path(_raw).expanduser()
    _labs, _, _ = _user_config_paths()
    if _labs is not None:
        return _labs
    return data_root() / "labs"


def benchmark_root() -> Path:
    """Alias for :func:`labs_root` (benchmarks are experiments in labs)."""
    return labs_root()


def data_dir() -> Path:
    """Return the directory for ephemeral / support data.

    Resolved from ``$MAS_LAB_DATA``; defaults to ``<data_root>/data``.

    Contains: trace-cache, standalone run records, logs, pipeline scratch.
    """
    _raw = os.environ.get(MAS_LAB_DATA_ENV, "").strip()
    return Path(_raw).expanduser() if _raw else data_root() / "data"


def lab_output() -> Path:
    """Return the directory for interactive demo / lab-config outputs.

    Defaults to ``<data_dir>/lab-output`` (not overridable by env — use
    ``MAS_LAB_DATA`` or ``MAS_DATA_ROOT`` to relocate the parent tree).
    """
    return data_dir() / "lab-output"


def trace_cache(explicit: str | None = None) -> Path:
    """Return the directory used for run trace caching.

    If *explicit* is provided it overrides everything else.
    Otherwise resolved from ``$MAS_TRACE_CACHE``; defaults to
    ``<data_dir>/trace-cache``.
    """
    if explicit:
        return Path(explicit).expanduser()
    _raw = os.environ.get(MAS_TRACE_CACHE_ENV, "").strip()
    if _raw:
        return Path(_raw).expanduser()
    _, _cache, _ = _user_config_paths()
    if _cache is not None:
        return _cache / "traces"
    return data_dir() / "trace-cache"


def data_cache(explicit: str | None = None) -> Path:
    """Return the directory used for pipeline step caching.

    Stores step fingerprints and (optionally) intermediate outputs so that
    pipeline steps are not re-executed unnecessarily — including after a
    benchmark archive is imported on another machine.

    If *explicit* is provided it overrides everything else.
    Otherwise resolved from ``$MAS_DATA_CACHE``; defaults to
    ``<data_dir>/data-cache``.
    """
    if explicit:
        return Path(explicit).expanduser()
    _raw = os.environ.get(MAS_DATA_CACHE_ENV, "").strip()
    if _raw:
        return Path(_raw).expanduser()
    _, _cache, _ = _user_config_paths()
    if _cache is not None:
        return _cache / "artifacts"
    return data_dir() / "data-cache"


def runs_root() -> Path:
    """Return the directory where agent run artefacts are stored.

    Resolved from ``$MAS_RUNS_ROOT``; defaults to ``<data_dir>/runs``.
    """
    _raw = os.environ.get(MAS_RUNS_ROOT_ENV, "").strip()
    if _raw:
        return Path(_raw).expanduser()
    _, _, _runs = _user_config_paths()
    if _runs is not None:
        return _runs
    return data_dir() / "runs"


def standalone_runs_root() -> Path:
    """Return the directory where standalone run records are stored.

    Resolved from ``$MAS_STANDALONE_RUNS_ROOT``; defaults to
    ``<data_dir>/standalone-runs``.
    """
    _raw = os.environ.get(MAS_STANDALONE_RUNS_ENV, "").strip()
    return Path(_raw).expanduser() if _raw else data_dir() / "standalone-runs"


# -----------------------------------------------------------------
# Display helper
# -----------------------------------------------------------------

def source_tag(
    specific_env: str | None = None,
    lab_config: bool = False,
) -> str:
    """Return a short human-readable string describing the path source.

    Used by ``mas-lab config`` to explain *why* a path has its current value.
    """
    if specific_env and os.environ.get(specific_env):
        return f"${specific_env}"
    if lab_config:
        return "lab-config.yaml"
    if os.environ.get(MAS_LABS_ROOT_ENV):
        return f"${MAS_LABS_ROOT_ENV} (derived)"
    if os.environ.get(MAS_DATA_ROOT_ENV):
        return f"${MAS_DATA_ROOT_ENV} (derived)"
    return "default"


# -----------------------------------------------------------------
# Shorthand path resolver
# -----------------------------------------------------------------

def resolve_run_artifact(
    shorthand: str,
    *,
    artifact: str = "events.jsonl",
) -> Path:
    """Resolve a lab-shorthand into an artifact path.

    *shorthand* is a ``/``-separated string of up to 5 segments::

        <lab>/<experiment>/<scenario>/<item>/<run>

    Each slash-separated component is matched against the directory names
    under :func:`labs_root`.  Trailing segments that are omitted default
    to the first (alphabetically sorted) child at that level.

    Args:
        shorthand: A ``/``-delimited path relative to labs_root, e.g.
            ``tutorials/t3-analysis/baseline/item1/r1``.
            Partial paths are expanded by picking the first child.
        artifact: The artifact filename to return.  Common values:
            ``"events.jsonl"`` (default, under ``traces/``)

    Returns:
        Absolute path to the requested artifact.

    Raises:
        FileNotFoundError: When no matching directory or artifact is found.

    Examples::

        resolve_run_artifact("tutorials/t3-analysis")
        # → ~/.mas-lab/labs/tutorials/t3-analysis/baseline/item1/r1/traces/events.jsonl

        resolve_run_artifact("tutorials/t3-analysis/baseline/item1/r1",
                             artifact="events.jsonl")
        # → ~/.mas-lab/labs/tutorials/t3-analysis/baseline/item1/r1/traces/events.jsonl
    """
    parts = [p for p in shorthand.strip("/").split("/") if p]
    root = labs_root()
    if not root.exists():
        raise FileNotFoundError(f"Labs root does not exist: {root}")

    cur = root
    for part in parts:
        candidate = cur / part
        if not candidate.is_dir():
            raise FileNotFoundError(
                f"Directory not found: {candidate}\n"
                f"Available: {', '.join(sorted(d.name for d in cur.iterdir() if d.is_dir())) or '(empty)'}"
            )
        cur = candidate

    # Auto-descend into the first child at each remaining level until we
    # reach a directory that contains the artifact (or its parent "traces/").
    MAX_DEPTH = 5  # safety: lab / experiment / scenario / item / run
    for _ in range(MAX_DEPTH):
        if _has_artifact(cur, artifact):
            break
        children = sorted(d for d in cur.iterdir() if d.is_dir())
        if not children:
            break
        cur = children[0]

    return _artifact_path(cur, artifact)


def _has_artifact(directory: Path, artifact: str) -> bool:
    """Check whether *directory* contains the requested artifact."""
    if artifact == "events.jsonl":
        return (directory / "traces" / "events.jsonl").exists()
    return (directory / artifact).exists()


def _artifact_path(directory: Path, artifact: str) -> Path:
    """Return the artifact path, raising if it doesn't exist."""
    if artifact == "events.jsonl":
        p = directory / "traces" / "events.jsonl"
    else:
        p = directory / artifact
    if not p.exists():
        raise FileNotFoundError(
            f"Artifact not found: {p}\n"
            f"Contents of {directory}: {', '.join(sorted(f.name for f in directory.iterdir())) if directory.exists() else '(missing)'}"
        )
    return p


def list_labs() -> list[str]:
    """Return the names of all lab directories under :func:`labs_root`."""
    root = labs_root()
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def workspace_relative_path(path: str | Path, *, start: Path | None = None) -> str:
    """Return *path* relative to the mas-workspace root when possible.

    Absolute paths under the workspace are stored as repo-relative strings in
    artefacts such as ``run_info.json``.  Paths already relative are normalized
    with forward slashes.
    """
    if not path:
        return ""
    raw = str(path).strip()
    if not raw:
        return ""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        return raw.replace("\\", "/")
    try:
        from mas.lab.workspace import find_workspace_root

        ws = find_workspace_root(start or p)
        if ws is not None:
            return str(p.resolve().relative_to(ws.resolve())).replace("\\", "/")
    except Exception:
        pass
    return raw.replace("\\", "/")
