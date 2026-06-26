#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""Lab tree and pipeline DAG rendering for benchmark show commands."""

from pathlib import Path

def _render_exp_tree(
    exp_yaml: "Path",
    verbose: int,
    depth: int,
    scenario_filter: "str | None",
    item_filter: "str | None",
    run_filter: "int | None",
    artifact_type_filter: "str | None",
    artifacts_only: bool,
    prefix: str,
    child_prefix: str,
) -> None:
    """Render one experiment subtree."""
    import json as _json

    from mas.lab.lab.config import MASExperimentConfig

    # Load experiment config
    try:
        exp = MASExperimentConfig.from_yaml(exp_yaml)
    except Exception as e:
        print(f"{prefix}{exp_yaml.parent.name}/  [config error: {e}]")
        return

    exp_dir_name = exp_yaml.parent.name
    data_dir: "Path | None" = getattr(exp, "output_dir", None)

    def _has_results(d: "Path | None") -> bool:
        if d is None or not d.exists():
            return False
        csv = d / "results.csv"
        if not csv.exists():
            return False
        # A header-only CSV is ~100 bytes; require at least one data row.
        if csv.stat().st_size < 150:
            return False
        try:
            import pandas as _pd0
            return len(_pd0.read_csv(csv)) > 0
        except Exception:
            return csv.stat().st_size > 150

    # Resolve status / row count
    if data_dir and data_dir.exists():
        results_csv = data_dir / "results.csv"
        if results_csv.exists():
            try:
                import pandas as _pd
                n_rows = len(_pd.read_csv(results_csv))
                status_str = f"✓  {n_rows} rows"
            except Exception:
                status_str = "✓  (results.csv present)"
        else:
            status_str = "⚑  no results.csv"
    else:
        status_str = "○  not run"

    print(f"{prefix}{exp_dir_name}/  [{exp.name}]  {status_str}")

    if data_dir is None or not data_dir.exists():
        return

    # Reserved top-level dir names that are not scenarios
    _NON_SCENARIO_DIRS = {"results", "plots", "runs", "otel", "traces"}

    # Collect scenario directories (skip hidden + reserved names)
    scenarios = sorted(
        d for d in data_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name not in _NON_SCENARIO_DIRS
    )
    if scenario_filter:
        scenarios = [s for s in scenarios if scenario_filter in s.name]

    # Sections to render: scenarios + optional artifacts + optional pipeline DAG
    _has_pipeline = verbose >= 3 and bool(getattr(exp, "pipeline", []))
    n_sections = len(scenarios) + (1 if verbose >= 1 else 0) + (1 if _has_pipeline else 0)

    if not artifacts_only and depth >= 2:
        for j, sc_dir in enumerate(scenarios):
            is_last_sc = (j == len(scenarios) - 1) and (verbose < 1)
            sc_prefix = child_prefix + ("└── " if is_last_sc else "├── ")
            sc_child = child_prefix + ("    " if is_last_sc else "│   ")

            # Collect item directories
            items = sorted(
                d for d in sc_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
            if item_filter:
                items = [it for it in items if item_filter in it.name]

            # Summarise runs for compact display
            item_summaries = []
            for it_dir in items:
                runs = sorted(
                    d for d in it_dir.iterdir()
                    if d.is_dir() and d.name.startswith("r")
                )
                if run_filter is not None:
                    runs = [r for r in runs if r.name == f"r{run_filter}"]

                statuses = []
                for r in runs:
                    metrics_path = r / "metrics.json"
                    if metrics_path.exists():
                        try:
                            info = _json.loads(metrics_path.read_text())
                            rq = info.get("run_quality", {})
                            s = rq.get("status", "?")
                            statuses.append("✓" if s == "ok" else "✗")
                        except Exception:
                            statuses.append("?")
                    elif (r / "run_info.json").exists() or (r / ".run_ref").exists():
                        statuses.append("✓")
                    else:
                        statuses.append("○")

                # Strip "item" prefix for display
                name = it_dir.name
                if name.startswith("item"):
                    name = name[4:]
                item_summaries.append((name, statuses))

            n_items = len(item_summaries)
            n_runs = max((len(s) for _, s in item_summaries), default=0)
            print(f"{sc_prefix}{sc_dir.name}/  ({n_items} items × {n_runs} runs)")

            # Expand items only when explicitly requested (filter or --depth item/run)
            if item_filter or run_filter is not None or depth >= 3:
                for k, (it_name, run_statuses) in enumerate(item_summaries):
                    is_last_it = k == len(item_summaries) - 1
                    it_prefix = sc_child + ("└── " if is_last_it else "├── ")
                    runs_str = "  ".join(
                        f"r{ri + 1}{s}" for ri, s in enumerate(run_statuses)
                    )
                    print(f"{it_prefix}{it_name}  {runs_str}")

    # Artifacts section
    if verbose >= 1:
        from mas.lab.artifacts import classify_file as _classify_file

        arts_is_last = not _has_pipeline
        arts_prefix = child_prefix + ("└── " if arts_is_last else "├── ")
        arts_child  = child_prefix + ("    " if arts_is_last else "│   ")

        # ----------------------------------------------------------------
        # Helpers
        # ----------------------------------------------------------------
        import hashlib as _hashlib

        def _artifact_id(p: "Path") -> str:
            try:
                return _hashlib.sha256(p.read_bytes()).hexdigest()[:8]
            except Exception:
                return "--------"

        def _fmt_path(p: "Path") -> str:
            try:
                return "~/" + str(p.relative_to(Path.home()))
            except ValueError:
                return str(p)

        # Build provenance map: filename → producing step name
        _provenance: dict[str, str] = {}
        for _step in getattr(exp, "pipeline", []):
            _sname = getattr(_step, "name", None) or getattr(_step, "type", "")
            _stype = getattr(_step, "type", "")
            _scfg  = getattr(_step, "config", {}) or {}
            for _key in ("output", "output_file"):
                _out = _scfg.get(_key, "")
                if _out and not str(_out).startswith("@"):
                    _provenance[Path(str(_out)).name] = _sname
            _schema_out = _PIPELINE_ARTIFACT_SCHEMA.get(_stype, {}).get("outputs", [])
            for _out_entry in _schema_out:
                if len(_out_entry) >= 5:
                    _, _, _cfg_k, _tmpl, _glob = _out_entry
                    if _glob and "." in _glob:
                        _provenance[_glob.lstrip("*/")] = _sname

        def _prov(p: "Path") -> str:
            fname = p.name
            note  = _provenance.get(fname, "")
            if not note:
                for k, v in _provenance.items():
                    if fname == k or fname.endswith(k.lstrip("*")):
                        note = v
                        break
            return f" ← {note}" if note else ""

        # Types that are implementation details, not user-facing artefacts
        _SKIP_TYPES = {"Ref", "FP"}

        _type_filter = artifact_type_filter

        # ----------------------------------------------------------------
        # Collect flat (experiment-level) artifacts
        # ----------------------------------------------------------------
        _flat_src: list = []  # (Path, info_str)

        results_csv = data_dir / "results.csv"
        if results_csv.exists():
            _size_kb = results_csv.stat().st_size / 1024
            try:
                import pandas as _pd2
                _n_rows = len(_pd2.read_csv(results_csv))
                _flat_src.append((results_csv, f"{_n_rows} rows, {_size_kb:.1f} KB"))
            except Exception:
                _flat_src.append((results_csv, f"{_size_kb:.1f} KB"))

        results_dir = data_dir / "results"
        if results_dir.exists():
            for _f in sorted(results_dir.iterdir()):
                if _f.is_file() and not _f.name.startswith("."):
                    _flat_src.append((_f, f"{_f.stat().st_size / 1024:.1f} KB"))

        if verbose >= 2:
            _cache_dir = data_dir / ".cache"
            if _cache_dir.exists():
                for _f in sorted(_cache_dir.iterdir()):
                    if _f.is_file():
                        _flat_src.append((_f, ""))

        # ----------------------------------------------------------------
        # Discover per-run structure from a representative run
        # ----------------------------------------------------------------
        _NON_SC = {"results", "plots", "runs", "otel", "traces"}
        _repr_run_dir: "Path | None" = None
        _per_run_files: list = []
        _n_runs_total: int = 0

        for _sc_d in sorted(data_dir.iterdir()):
            if not _sc_d.is_dir() or _sc_d.name.startswith(".") or _sc_d.name in _NON_SC:
                continue
            for _it_d in sorted(_sc_d.iterdir()):
                if not _it_d.is_dir() or _it_d.name.startswith("."):
                    continue
                for _r_d in sorted(_it_d.iterdir()):
                    if not _r_d.is_dir() or _r_d.name.startswith("."):
                        continue
                    _n_runs_total += 1
                    if _repr_run_dir is None:
                        _repr_run_dir = _r_d
                        _per_run_files = sorted(
                            _fp.name for _fp in _r_d.iterdir() if _fp.is_file()
                        )

        # ----------------------------------------------------------------
        # Build row lists: ("art", name, art_id, type_abbrev, info_str)
        # ----------------------------------------------------------------
        _flat_rows: list = []
        for _ap, _ai in _flat_src:
            _ft = _classify_file(_ap)
            if _ft.abbrev in _SKIP_TYPES:
                continue
            if _type_filter and _ft.abbrev.lower() != _type_filter.lower():
                continue
            _flat_rows.append((_ap.name, _artifact_id(_ap), _ft.abbrev,
                                f"{_ai}{_prov(_ap)}" if _ai else _prov(_ap).lstrip(),
                                _fmt_path(_ap)))

        _pr_rows: list = []
        if _repr_run_dir is not None:
            for _fname in _per_run_files:
                _fpath = _repr_run_dir / _fname
                if not _fpath.is_file():
                    continue
                _ft = _classify_file(_fpath)
                if _ft.abbrev in _SKIP_TYPES:
                    continue
                if _type_filter and _ft.abbrev.lower() != _type_filter.lower():
                    continue
                _size_s = f"{_fpath.stat().st_size / 1024:.1f} KB"
                _pr_rows.append((_fname, _artifact_id(_fpath), _ft.abbrev,
                                  f"{_size_s}{_prov(_fpath)}",
                                  _fmt_path(_fpath)))

        has_per_run = bool(_repr_run_dir) and (bool(_pr_rows) or not _type_filter)

        # ----------------------------------------------------------------
        # Compute column widths across ALL rows (flat + per-run sub-rows)
        # ----------------------------------------------------------------
        _ID_W = 8
        _all_type_abbrevs = [r[2] for r in _flat_rows] + [r[2] for r in _pr_rows]
        _TYPE_W = max((len(t) for t in _all_type_abbrevs), default=6)

        # col1 = tree-art prefix + filename; compute max length
        _arts_indent = len(arts_child) + 4      # "├── " = 4 chars
        _pr_indent   = len(arts_child) + 4 + 4  # "    " + "├── " (child of [per-run ×N])
        _pr_hdr_len  = _arts_indent + len(f"[per-run × {_n_runs_total}]")
        _col1_lengths = (
            [_arts_indent + len(r[0]) for r in _flat_rows]
            + [_pr_indent  + len(r[0]) for r in _pr_rows]
            + ([_pr_hdr_len] if has_per_run else [])
        )
        _COL1_W = max(_col1_lengths, default=_arts_indent + 20) + 2

        def _print_row(col1: str, art_id: str, type_abbrev: str, info: str) -> None:
            _id_s   = f"{art_id:<{_ID_W}}"   if art_id   else " " * _ID_W
            _type_s = f"{type_abbrev:<{_TYPE_W}}" if type_abbrev else " " * _TYPE_W
            _info_s = f"  {info}" if info else ""
            print(f"{col1:<{_COL1_W}}  {_id_s}  {_type_s}{_info_s}")

        # ----------------------------------------------------------------
        # Print
        # ----------------------------------------------------------------
        print(f"{arts_prefix}[artifacts]")

        for _ridx, (_name, _aid, _type, _info, _path) in enumerate(_flat_rows):
            _is_last = (_ridx == len(_flat_rows) - 1) and not has_per_run
            _cont    = arts_child + ("    " if _is_last else "│   ")
            _tree    = arts_child + ("└── " if _is_last else "├── ")
            _print_row(f"{_tree}{_name}", _aid, _type, _info)
            print(f"{_cont}  {_path}")

        if has_per_run:
            pr_prefix = arts_child + "└── "
            pr_child  = arts_child + "    "
            _sc_dirs  = [d for d in data_dir.iterdir()
                         if d.is_dir() and not d.name.startswith(".") and d.name not in _NON_SC]
            _n_sc    = len(_sc_dirs)
            _n_items = max((sum(1 for d in s.iterdir() if d.is_dir() and not d.name.startswith("."))
                            for s in _sc_dirs), default=0)
            _n_r     = max((_n_runs_total // (_n_sc * _n_items)) if (_n_sc * _n_items) else 0, 1)

            _pr_hdr_col1 = f"{pr_prefix}[per-run \u00d7 {_n_runs_total}]"
            _pr_hdr_info = f"{_n_sc} scenarios \u00d7 {_n_items} items \u00d7 {_n_r} runs"
            _print_row(_pr_hdr_col1, "", "", _pr_hdr_info)

            # At -vv show the path pattern and a concrete example
            if verbose >= 2:
                _base = _fmt_path(data_dir)
                print(f"{pr_child}  pattern: {_base}/<scenario>/item<id>/r<N>/")
                print(f"{pr_child}  example: {_fmt_path(_repr_run_dir)}")

            for _ridx, (_name, _aid, _type, _info, _path) in enumerate(_pr_rows):
                _is_last = _ridx == len(_pr_rows) - 1
                _cont    = pr_child + ("    " if _is_last else "\u2502   ")
                _tree    = pr_child + ("\u2514\u2500\u2500 " if _is_last else "\u251c\u2500\u2500 ")
                _print_row(f"{_tree}{_name}", _aid, _type, _info)
                print(f"{_cont}  {_path}")

    # Pipeline DAG section (verbose >= 3)
    if _has_pipeline:
        _render_pipeline_dag(
            steps=exp.pipeline,
            data_dir=data_dir,
            prefix=child_prefix + "└── ",
            child_prefix=child_prefix + "    ",
        )


# ---------------------------------------------------------------------------
# _render_pipeline_dag — show pipeline step DAG with artifact lineage (-vvv)
# ---------------------------------------------------------------------------

# Artifact descriptors:
#   inputs:  (label, materialized, glob_pattern_for_count | None)
#   outputs: (label, materialized, config_key | None, default_template | None, glob_pat | None)
_PIPELINE_ARTIFACT_SCHEMA: dict = {
    "eval_mce": {
        "inputs":  [("events.jsonl per run", False, None)],
        "outputs": [("metrics.json per run", True, None, None, "**/metrics.json")],
    },
    "eval_mce_batch": {
        "inputs":  [("events.jsonl per run", False, None)],
        "outputs": [("metrics.json per run", True, None, None, "**/metrics.json")],
    },
    "eval_batch": {
        "inputs":  [("events.jsonl per run", False, None)],
        "outputs": [("metrics.json per run", True, None, None, "**/metrics.json")],
    },
    "collect_metrics": {
        "inputs":  [("metrics.json per run", True, "**/metrics.json")],
        "outputs": [("results.csv", True, "output", "{output_dir}/results.csv", None)],
    },
    "to_dataframe": {
        "inputs":  [("metrics.json per run", True, "**/metrics.json")],
        "outputs": [("data.csv", True, "output", "{output_dir}/data.csv", None)],
    },
    "join_dataframe": {
        "inputs":  [("data.csv", True, None)],
        "outputs": [("joined.csv", True, "output", "{output_dir}/joined.csv", None)],
    },
    "plotnine": {
        "inputs":  [("results.csv", True, None)],
        "outputs": [("figure", True, "output", None, None)],
    },
    "metrics_comparison_plot": {
        "inputs":  [("results.csv", True, None)],
        "outputs": [("comparison.png", True, "output", "{output_dir}/comparison.png", None)],
    },
}


def _render_pipeline_dag(
    steps: list,
    data_dir: "Path",
    prefix: str,
    child_prefix: str,
) -> None:
    """Render the pipeline DAG with artifact lineage at -vvv verbosity.

    Legend:
      ●  materialized artifact (written to disk / already exists)
      ○  virtual artifact (in-memory / not directly persisted by this step)
      ←  input consumed by step
      →  output produced by step
    """

    def _subst(s: str) -> str:
        return s.replace("{output_dir}", str(data_dir))

    def _fmt_path(p: "Path") -> str:
        try:
            return "~/" + str(p.relative_to(Path.home()))
        except ValueError:
            return str(p)

    def _file_info(p: "Path") -> str:
        if not p.exists():
            return "missing"
        size_kb = p.stat().st_size / 1024
        if p.suffix == ".csv" and size_kb > 0:
            try:
                import pandas as _pd3
                n = len(_pd3.read_csv(p))
                return f"{n} rows, {size_kb:.1f} KB"
            except Exception:
                logger.debug('suppressed', exc_info=True)
        return f"{size_kb:.1f} KB"

    print(f"{prefix}[pipeline]  legend: ● materialized  ○ virtual  ← in  → out")

    for i, step in enumerate(steps):
        is_last = i == len(steps) - 1
        step_pfx   = child_prefix + ("└── " if is_last else "├── ")
        step_child = child_prefix + ("    " if is_last else "│   ")

        step_name  = step.name or step.type
        scope_note = f"  scope:{step.scope}" if getattr(step, "scope", "") else (
            "  per-scenario" if getattr(step, "per_scenario", False) else ""
        )
        deps_note  = f"  ← {', '.join(step.depends_on)}" if getattr(step, "depends_on", []) else ""
        print(f"{step_pfx}{step_name}  [{step.type}]{scope_note}{deps_note}")

        schema  = _PIPELINE_ARTIFACT_SCHEMA.get(step.type, {})
        cfg     = getattr(step, "config", {}) or {}
        lines: list[str] = []

        # Inputs
        for label, materialized, glob_pat in schema.get("inputs", []):
            sym  = "●" if materialized else "○"
            note = "" if materialized else "  (virtual)"
            if glob_pat and data_dir:
                count     = sum(1 for _ in data_dir.rglob(glob_pat))
                count_str = f"  ×{count}" if count else ""
            else:
                count_str = ""
            lines.append(f"← {sym}  {label}{count_str}{note}")

        # Outputs
        for label, materialized, config_key, default_tmpl, glob_pat in schema.get("outputs", []):
            sym = "●" if materialized else "○"

            # Resolve actual path: config key > default template > glob
            actual: "Path | None" = None
            if config_key and config_key in cfg:
                raw = str(cfg[config_key])
                if not raw.startswith("@"):      # skip @step-ref data sources
                    actual = Path(_subst(raw))
            elif default_tmpl:
                actual = Path(_subst(default_tmpl))

            if actual:
                info        = _file_info(actual)
                exist_mark  = " ✓" if actual.exists() else " ✗"
                lines.append(f"→ {sym}  {_fmt_path(actual)}  ({info}){exist_mark}")
            elif glob_pat and data_dir:
                count     = sum(1 for _ in data_dir.rglob(glob_pat))
                count_str = f"  ×{count}" if count else ""
                lines.append(f"→ {sym}  {label}{count_str}")
            else:
                lines.append(f"→ {sym}  {label}")

        for j, line in enumerate(lines):
            is_last_line = j == len(lines) - 1
            line_pfx = step_child + ("└── " if is_last_line else "├── ")
            print(f"{line_pfx}{line}")

