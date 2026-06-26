#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

"""High-level object model for navigating lab experiments and their results.

Provides ``Lab → Experiment → Scenario → Run`` navigation with artifact
access and a ``QuerySet`` for fluent run filtering.

This is the API documented in ``docs/api-reference.md``.  It wraps the
low-level :class:`~mas.lab.benchmark.results.ExperimentResults` filesystem
model and adds:

- experiment discovery from a lab directory tree
- ``vars`` from ``experiment.yaml``
- ``artifacts()`` — typed artifact access (DataFrameArtifact, PlotFile, …)
- ``QuerySet`` — ``.one()``, ``.filter()``, ``.all()``, ``.first()``
- ``Run.metrics`` / ``Run.trajectory`` / ``Run.status``

Example::

    from mas.lab.labs import Lab

    lab = Lab()                                # CWD must be a .lab directory
    lab = Lab("labs/design-space.lab")         # explicit path
    exp = lab.experiment('01')                 # prefix match

    # Iterate
    for scenario in exp.scenarios:
        print(scenario.name, len(scenario.runs))

    # QuerySet
    run = exp.runs.one()
    df  = exp.artifacts('results').load()

    # Tidy DataFrame via ExperimentResults
    tidy = exp.collect_dataframe('metrics.json', flatten='session')
"""

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

import pandas as pd

from mas.lab.benchmark.results import (
    ExperimentResults,
    ItemView,
    RunView,
    ScenarioView,
)

# ── Palette ──────────────────────────────────────────────────────────────────

class Palette:
    """Auto-assigning color palette — maps string keys to hex colors.

    Behaves like a dict: ``palette['scenario-name']`` returns a stable hex color
    auto-assigned from the tab10 color cycle.  Pass to any plot function that
    accepts a color mapping.

    Example::

        lab = Lab()
        p = lab.palette
        execution_chain_graph(run.trajectory, level='agents', palette=p)
    """

    _COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]

    def __init__(self) -> None:
        self._mapping: Dict[str, str] = {}
        self._idx: int = 0

    def __getitem__(self, key: str) -> str:
        if key not in self._mapping:
            self._mapping[key] = self._COLORS[self._idx % len(self._COLORS)]
            self._idx += 1
        return self._mapping[key]

    def __contains__(self, key: object) -> bool:
        return key in self._mapping

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            return self[key]
        except Exception:
            return default

    def seed(self, keys: List[str]) -> "Palette":
        """Pre-assign colors to a list of keys (deterministic ordering)."""
        for k in keys:
            _ = self[k]  # trigger assignment
        return self

    def __repr__(self) -> str:
        return f"Palette({self._mapping})"


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_experiment_yaml(yaml_path: Path) -> Dict[str, Any]:
    """Load experiment YAML without triggering the full MASExperimentConfig machinery."""
    import yaml
    with open(yaml_path) as f:
        raw = yaml.safe_load(f) or {}
    # Top-level key is either "experiment:" or bare dict
    return raw.get("experiment", raw)


# ── Artifact types ────────────────────────────────────────────────────────────

class DataFrameArtifact:
    """A parquet or CSV file that loads as a :class:`~pandas.DataFrame`.

    Attributes
    ----------
    name:
        Artifact stem (e.g. ``"results"``, ``"impact"``).
    path:
        Absolute path to the file.
    """

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path

    def load(self) -> pd.DataFrame:
        """Load the DataFrame (parquet preferred, CSV fallback)."""
        if self.path.suffix == ".parquet":
            return pd.read_parquet(self.path)
        return pd.read_csv(self.path)

    def __repr__(self) -> str:
        return f"DataFrameArtifact({self.name!r}, {self.path.name})"


class PlotFile:
    """A generated visualisation file (PNG/SVG/HTML).

    Attributes
    ----------
    name:
        File stem.
    path:
        Absolute path to the file.
    format:
        ``"png"``, ``"svg"``, or ``"html"``.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.stem
        self.format = path.suffix.lstrip(".")

    def display(self, width: int = 900) -> None:
        """Render inline in a Jupyter notebook."""
        from IPython.display import display as _display, Image, SVG, HTML
        if self.format == "svg":
            _display(SVG(filename=str(self.path)))
        elif self.format == "html":
            _display(HTML(self.path.read_text()))
        else:
            _display(Image(filename=str(self.path), width=width))

    def __repr__(self) -> str:
        return f"PlotFile({self.name!r}, {self.format})"


# ── QuerySet ─────────────────────────────────────────────────────────────────

class QuerySet:
    """Fluent collection of :class:`Run` objects.

    Methods
    -------
    all() -> list[Run]
    one() -> Run            raises if count != 1
    first() -> Run | None
    filter(**kwargs) -> QuerySet
    count() -> int
    """

    def __init__(self, runs: List["Run"]) -> None:
        self._runs = runs

    def all(self) -> List["Run"]:
        return list(self._runs)

    def one(self) -> "Run":
        if len(self._runs) != 1:
            raise ValueError(
                f"QuerySet.one() expected exactly 1 run, got {len(self._runs)}"
            )
        return self._runs[0]

    def first(self) -> Optional["Run"]:
        return self._runs[0] if self._runs else None

    def count(self) -> int:
        return len(self._runs)

    def filter(self, **kwargs: Any) -> "QuerySet":
        """Filter runs by attribute values.

        Example::

            baseline = exp.runs.filter(scenario="baseline")
        """
        result = []
        for run in self._runs:
            if all(getattr(run, k, None) == v for k, v in kwargs.items()):
                result.append(run)
        return QuerySet(result)

    def __iter__(self) -> Iterator["Run"]:
        return iter(self._runs)

    def __len__(self) -> int:
        return len(self._runs)

    def __repr__(self) -> str:
        return f"QuerySet({len(self._runs)} runs)"


# ── Run ───────────────────────────────────────────────────────────────────────

class Run:
    """One agent execution (wraps :class:`~mas.lab.benchmark.results.RunView`).

    Attributes
    ----------
    run_id:
        Numeric run index as a string (``"1"``, ``"2"``, …).
    item_id:
        Item identifier (e.g. ``"analysis-1"``).
    scenario:
        Scenario name this run belongs to.
    status:
        ``"completed"``, ``"failed"``, or ``"unknown"`` from ``run_info.json``.
    metrics:
        Dict of metric → value loaded from ``metrics.json``.
    """

    def __init__(
        self,
        view: RunView,
        item_id: str,
        scenario: str,
    ) -> None:
        self._view = view
        self.run_id = f"{scenario}__{item_id}__r{view.run_id}"
        self.item_id = item_id
        self.scenario = scenario

    # ── lazy properties ──────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._view.path

    @property
    def status(self) -> str:
        ri = self._view.load_json("run_info.json")
        return ri.get("status", "unknown")

    @property
    def metrics(self) -> Dict[str, Any]:
        doc = self._view.load_json("metrics.json")
        session = doc.get("session", {})
        return {k: v.get("value") if isinstance(v, dict) else v for k, v in session.items()}

    @property
    def trajectory(self) -> Dict[str, Any]:
        """Full execution trace from the trace cache (``result.json``)."""
        run_ref = self._view.path / ".run_ref"
        if not run_ref.exists():
            return {}
        try:
            from mas.lab.paths import trace_cache
            cache_hash = run_ref.read_text(encoding="utf-8").strip()
            result_path = trace_cache() / cache_hash / "result.json"
            if result_path.exists():
                return json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug('suppressed', exc_info=True)
        return {}

    def artifacts(
        self,
        name: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> Any:
        """Artifacts in this run's output directory.

        Mirrors :meth:`Experiment.artifacts`:

        - ``run.artifacts('stats')`` → single :class:`DataFrameArtifact` by name
        - ``run.artifacts()`` → list of all artifacts
        - ``run.artifacts(kind='dataframe')`` → list of DataFrame artifacts
        """
        arts = _collect_artifacts(self._view.path, kind=kind)
        if name is not None:
            matches = [a for a in arts if a.name == name]
            if not matches:
                raise KeyError(
                    f"No artifact {name!r} in run {self.run_id!r} "
                    f"(available: {[a.name for a in arts]})"
                )
            return matches[0]
        return arts

    def __repr__(self) -> str:
        return f"Run({self.run_id!r})"


# ── Scenario ──────────────────────────────────────────────────────────────────

class Scenario:
    """One scenario (configuration variant) inside an experiment.

    Wraps :class:`~mas.lab.benchmark.results.ScenarioView` and adds
    typed ``runs`` and ``tests``.

    Attributes
    ----------
    name:
        Scenario directory name (e.g. ``"pattern-cot"``).
    """

    def __init__(self, view: ScenarioView) -> None:
        self._view = view
        self.name = view.scenario_id

    @property
    def runs(self) -> List[Run]:
        """All runs across all items for this scenario."""
        result: List[Run] = []
        for item in self._view.items:
            for rv in item.runs:
                result.append(Run(rv, item_id=item.item_id, scenario=self.name))
        return result

    @property
    def items(self) -> List[ItemView]:
        return self._view.items

    @property
    def tests(self) -> List[Dict[str, Any]]:
        """Load test cases from ``dataset.yaml`` or the run inputs (best-effort)."""
        tests: List[Dict[str, Any]] = []
        for item in self._view.items:
            for rv in item.runs:
                ri = rv.load_json("run_info.json")
                if ri:
                    tests.append({
                        "item_id": item.item_id,
                        "run_id": rv.run_id,
                        "input": ri.get("input") or ri.get("user_prompt", ""),
                        "model": ri.get("model", ""),
                    })
                    break  # one representative per item
        return tests

    def __repr__(self) -> str:
        return f"Scenario({self.name!r})"


# ── Experiment ────────────────────────────────────────────────────────────────

class Experiment:
    """One experiment configuration and results.

    Wraps :class:`~mas.lab.benchmark.results.ExperimentResults` and exposes:

    - ``scenarios`` — typed scenario list
    - ``runs`` — :class:`QuerySet` over all runs
    - ``artifacts()`` — typed artifact access
    - ``vars`` — experiment config variables
    - ``collect_dataframe()`` — tidy fan-in (delegates to ExperimentResults)

    Parameters
    ----------
    yaml_path:
        Path to ``experiment.yaml`` inside the lab directory.
    """

    def __init__(self, yaml_path: Path) -> None:
        self._yaml_path = yaml_path
        self._raw = _load_experiment_yaml(yaml_path)
        self.name: str = self._raw.get("name", yaml_path.parent.name)
        self._output_dir: Optional[Path] = None

    @property
    def path(self) -> Path:
        return self._yaml_path.parent

    @property
    def output_dir(self) -> Path:
        """Resolved benchmark output directory (lazy)."""
        if self._output_dir is None:
            self._output_dir = self._resolve_output_dir()
        return self._output_dir

    def _resolve_output_dir(self) -> Path:
        """Mirror the resolution logic from MASRunBase._load_base_fields."""
        from mas.lab import paths as _paths

        # Explicit output_dir in YAML (deprecated but still supported)
        if "output_dir" in self._raw:
            p = Path(self._raw["output_dir"]).expanduser()
            return p if p.is_absolute() else (self._yaml_path.parent / p).resolve()

        exp_name = self._raw.get("name", self._yaml_path.parent.name)

        # Discover lab name from the yaml path (same heuristic as config.py)
        lab_name: Optional[str] = None
        for parent in self._yaml_path.parents:
            if parent.name.endswith(".lab"):
                lab_name = parent.name[:-4]  # strip ".lab"
                break

        if lab_name:
            candidate = _paths.labs_root() / lab_name / exp_name
        else:
            candidate = _paths.benchmark_root() / exp_name

        return candidate

    @property
    def results(self) -> ExperimentResults:
        """Low-level :class:`~mas.lab.benchmark.results.ExperimentResults` wrapper."""
        return ExperimentResults.from_output_dir(self.output_dir)

    @property
    def scenarios(self) -> List[Scenario]:
        return [Scenario(sv) for sv in self.results.scenarios]

    def scenario(self, name: str) -> Scenario:
        """Get a scenario by exact name."""
        for s in self.scenarios:
            if s.name == name:
                return s
        raise KeyError(f"Scenario {name!r} not found in {self.name!r}")

    @property
    def runs(self) -> QuerySet:
        """All runs across all scenarios as a :class:`QuerySet`."""
        result: List[Run] = []
        for scenario in self.scenarios:
            result.extend(scenario.runs)
        return QuerySet(result)

    @property
    def vars(self) -> Dict[str, Any]:
        """Experiment-level variables from ``experiment.yaml``."""
        return dict(self._raw.get("vars", {}))

    @property
    def benchmark_path(self) -> Path:
        return self.output_dir

    def artifacts(
        self,
        name: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> Any:
        """Return artifacts from the experiment output directory.

        Behaviour depends on arguments:

        - ``artifacts()`` → ``list[DataFrameArtifact | PlotFile]`` — all artifacts
        - ``artifacts('impact')`` → single ``DataFrameArtifact`` by name (raises if not found)
        - ``artifacts(kind='plot_file')`` → ``list[PlotFile]``

        This matches the usage in notebooks::

            art = exp.artifacts('impact')   # → DataFrameArtifact
            df  = art.load()

        Parameters
        ----------
        name:
            Artifact stem (e.g. ``"impact"``, ``"results"``).
            When provided, returns a **single artifact** directly.
        kind:
            ``"dataframe"``, ``"plot_file"``, or ``None`` for all.
        """
        arts = _collect_artifacts(self.output_dir, kind=kind)
        if name is not None:
            matches = [a for a in arts if a.name == name]
            if not matches:
                raise KeyError(
                    f"No artifact {name!r} in {self.name!r} (available: "
                    f"{[a.name for a in arts]})"
                )
            return matches[0]
        return arts

    def collect_dataframe(
        self,
        filename: str,
        flatten: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fan-in per-run JSON into an experiment-level tidy DataFrame.

        Delegates to :meth:`~mas.lab.benchmark.results.ExperimentResults.collect_dataframe`.
        """
        return self.results.collect_dataframe(filename, flatten=flatten)

    def __repr__(self) -> str:
        try:
            n_scenarios = len(self.results.scenarios)
            n_runs = sum(
                len(item.runs)
                for sc in self.results.scenarios
                for item in sc.items
            )
            return f"Experiment(name={self.name!r}, scenarios={n_scenarios}, runs={n_runs})"
        except Exception:
            return f"Experiment(name={self.name!r})"


# ── Lab ───────────────────────────────────────────────────────────────────────

class Lab:
    """Top-level access point for a ``.lab`` directory.

    Parameters
    ----------
    path:
        Lab root directory.  Defaults to the current working directory.
    name:
        Optional display name override.

    Examples
    --------
    ::

        lab = Lab()                              # CWD must be a .lab directory
        lab = Lab("labs/design-space.lab")       # explicit path

        exp = lab.experiment("01")               # prefix match
        exp = lab.experiment("design-patterns")  # substring match

        for exp in lab.experiments():
            print(exp.name, len(exp.runs))
    """

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        name: Optional[str] = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve() if path else Path.cwd()
        _raw_name = self.path.name
        self.name = name or (_raw_name[:-4] if _raw_name.endswith(".lab") else _raw_name)
        self._palette: Optional[Palette] = None

    @property
    def palette(self) -> Palette:
        """Auto-assigning color palette for this lab's scenarios.

        Stable colors are auto-assigned from the tab10 cycle, seeded lazily from
        all scenarios found in the lab's experiments.

        Usage::

            p = lab.palette
            execution_chain_graph(run.trajectory, level='agents', palette=p)
        """
        if self._palette is None:
            p = Palette()
            # Seed from all scenario names found in the lab for stable ordering
            try:
                for exp in self.experiments():
                    for sc in exp.scenarios:
                        _ = p[sc.name]  # trigger assignment
            except Exception:
                logger.debug('suppressed', exc_info=True)
            self._palette = p
        return self._palette

    def experiment(self, name: str) -> Experiment:
        """Find an experiment by prefix or substring match.

        Resolution order:
        1. Exact match on the folder name.
        2. Prefix match (``"01"`` → ``"01-design-patterns"``).
        3. Substring match.

        Raises ``KeyError`` if no match or if more than one prefix/substring
        match exists.
        """
        candidates = self._discover_experiment_yamls()

        # 1. exact
        for yaml_path in candidates:
            if yaml_path.parent.name == name:
                return Experiment(yaml_path)

        # 2. prefix
        prefix_matches = [p for p in candidates if p.parent.name.startswith(name)]
        if len(prefix_matches) == 1:
            return Experiment(prefix_matches[0])
        if len(prefix_matches) > 1:
            raise KeyError(
                f"Ambiguous prefix {name!r}: matches "
                f"{[p.parent.name for p in prefix_matches]}"
            )

        # 3. substring
        sub_matches = [p for p in candidates if name in p.parent.name]
        if len(sub_matches) == 1:
            return Experiment(sub_matches[0])
        if len(sub_matches) > 1:
            raise KeyError(
                f"Ambiguous name {name!r}: matches "
                f"{[p.parent.name for p in sub_matches]}"
            )

        raise KeyError(f"No experiment matching {name!r} under {self.path}")

    def experiments(self) -> List[Experiment]:
        """All experiments in this lab, sorted by folder name."""
        return [Experiment(p) for p in self._discover_experiment_yamls()]

    def _discover_experiment_yamls(self) -> List[Path]:
        """Discover experiment manifests anywhere under the lab (explicit ``experiment:`` key)."""
        from mas.lab.controller.lab_registry import _DISCOVERY_SKIP_DIRS, _iter_library_yaml
        from mas.ctl.validate.schemas import declared_kind
        from mas.runtime.spec.source import load_yaml_file

        yamls: List[Path] = []
        for path in _iter_library_yaml(self.path):
            rel_parts = path.relative_to(self.path).parts
            if _DISCOVERY_SKIP_DIRS.intersection(rel_parts):
                continue
            try:
                doc = load_yaml_file(path)
            except Exception:
                continue
            if declared_kind(doc) == "experiment":
                yamls.append(path)
        return sorted(yamls)

    def __repr__(self) -> str:
        try:
            n = len(self._discover_experiment_yamls())
        except Exception:
            n = 0
        return f"Lab(name={self.name!r}, experiments={n})"


# ── artifact collection ───────────────────────────────────────────────────────

_DF_SUFFIXES  = {".parquet", ".csv"}
_PLOT_SUFFIXES = {".png", ".svg", ".html"}


def _collect_artifacts(
    directory: Path,
    kind: Optional[str] = None,
) -> List[Any]:
    """Scan *directory* for known artifact types."""
    if not directory.is_dir():
        return []

    results: List[Any] = []
    # Also search one level into plots/ subdirectory
    search_dirs = [directory, directory / "plots"]

    for d in search_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            if kind in (None, "dataframe") and p.suffix in _DF_SUFFIXES:
                results.append(DataFrameArtifact(p.stem, p))
            elif kind in (None, "plot_file") and p.suffix in _PLOT_SUFFIXES:
                results.append(PlotFile(p))

    return results
