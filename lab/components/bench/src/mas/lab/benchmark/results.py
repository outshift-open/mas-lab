#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Structured, API-based access to benchmark output directories.

The benchmark writes results in this layout::

    <output_dir>/
        <scenario_id>/
            item<item_id>/
                r<n>/
                    metrics.json
                    run_info.json
                    ...
        metadata.yaml
        results.csv
        plots/

:class:`ExperimentResults` wraps an ``output_dir`` and exposes
``scenarios → items → runs`` as typed collections, so downstream
code never has to glob the filesystem directly.

Example::

    from mas.lab.benchmark.results import ExperimentResults

    exp = ExperimentResults.from_output_dir(
        "labs_root()/design-space/design-patterns-qa"
    )

    for scenario in exp.scenarios:
        print(scenario.scenario_id)
        for item in scenario.items:
            for run in item.runs:
                data = run.load_json("metrics.json")

    # Or build a tidy experiment-level DataFrame in one call:
    df = exp.collect_dataframe("metrics.json", flatten="session")
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# ── naming conventions ──────────────────────────────────────────────────────
# Benchmark always creates:  <output_dir>/<scenario>/item<id>/r<n>/
# These regexes encode that convention once; consumers see clean IDs.
_RUN_RE  = re.compile(r'^r(\d+)$')         # "r1" → "1"
_ITEM_RE = re.compile(r'^item(.+)$')        # "itemanalysis-1" → "analysis-1"

# Directory names inside output_dir that are NOT scenario dirs.
_SKIP_NAMES = frozenset({"metadata.yaml", "results.csv", "plots", ".benchmark.lock"})


# ── leaf: one run ────────────────────────────────────────────────────────────

class RunView:
    """One execution run (``r1``, ``r2``, …) inside a test item.

    Attributes
    ----------
    path : Path
        Absolute path to the run directory.
    run_id : str
        Numeric run index as a string (``"1"``, ``"2"``, …).  The ``"r"``
        prefix is stripped so callers can do ``int(run.run_id)`` cleanly.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        m = _RUN_RE.match(path.name)
        self.run_id = m.group(1) if m else path.name

    # ------------------------------------------------------------------ I/O

    def load_json(self, filename: str) -> Dict[str, Any]:
        """Load *filename* from this run directory.

        Returns an empty dict if the file is absent rather than raising.
        """
        target = self.path / filename
        if not target.exists():
            return {}
        return json.loads(target.read_text(encoding="utf-8"))

    def load_dataframe(
        self,
        filename: str,
        flatten: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load *filename* as a :class:`~pandas.DataFrame`.

        Parameters
        ----------
        filename:
            JSON file relative to this run directory.
        flatten:
            When set, expand ``data[flatten]`` (a dict) into one row per key.
            The key becomes a ``metric`` column; all other scalar values in
            the nested dict become columns.  This is how ``metrics.json``'s
            ``"session"`` block is unwound.

        Returns an empty DataFrame if the file is absent.
        """
        data = self.load_json(filename)
        if not data:
            return pd.DataFrame()

        if flatten:
            nested = data.get(flatten, {})
            rows: list[dict] = []
            for key, entry in nested.items():
                if isinstance(entry, dict):
                    row: dict = {"metric": key}
                    row.update(entry)
                    rows.append(row)
                else:
                    rows.append({"metric": key, "value": entry})
            return pd.DataFrame(rows)

        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.DataFrame([data])

    def __repr__(self) -> str:
        return f"RunView(r{self.run_id}, {self.path.parent.parent.name}/{self.path.parent.name})"


# ── mid: one test item ───────────────────────────────────────────────────────

class ItemView:
    """One test item (input case) inside a scenario.

    Attributes
    ----------
    path : Path
        Absolute path to the item directory (``item<item_id>``).
    item_id : str
        Item identifier with the ``"item"`` prefix stripped
        (e.g. ``"analysis-1"``, ``"mn1"``).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        m = _ITEM_RE.match(path.name)
        self.item_id = m.group(1) if m else path.name

    @property
    def runs(self) -> List[RunView]:
        """All runs for this item, sorted by run index."""
        views = [
            RunView(d)
            for d in self.path.iterdir()
            if d.is_dir() and _RUN_RE.match(d.name)
        ]
        return sorted(views, key=lambda r: int(r.run_id))

    def __repr__(self) -> str:
        return f"ItemView({self.item_id!r})"


# ── top: one scenario ────────────────────────────────────────────────────────

class ScenarioView:
    """One scenario (configuration variant) inside an experiment output.

    Attributes
    ----------
    path : Path
        Absolute path to the scenario directory.
    scenario_id : str
        Scenario identifier (directory name, e.g. ``"pattern-cot"``).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.scenario_id = path.name

    @property
    def items(self) -> List[ItemView]:
        """All test items for this scenario, sorted by item_id."""
        views = [
            ItemView(d)
            for d in self.path.iterdir()
            if d.is_dir() and _ITEM_RE.match(d.name)
        ]
        return sorted(views, key=lambda i: i.item_id)

    def __repr__(self) -> str:
        return f"ScenarioView({self.scenario_id!r})"


# ── root: experiment output directory ────────────────────────────────────────

class ExperimentResults:
    """Structured access to one experiment's output directory.

    Wraps ``<output_dir>/`` and exposes the full
    ``scenarios → items → runs`` hierarchy as typed objects.

    Parameters
    ----------
    output_dir : Path | str
        The experiment output directory that contains one sub-directory
        per scenario.

    Examples
    --------
    Iterate the hierarchy manually::

        exp = ExperimentResults.from_output_dir(
            "labs_root()/design-space/design-patterns-qa"
        )
        for scenario in exp.scenarios:
            for item in scenario.items:
                for run in item.runs:
                    data = run.load_json("metrics.json")

    Build a tidy, experiment-level DataFrame in one call::

        df = exp.collect_dataframe("metrics.json", flatten="session")
        # columns: scenario, item_id, run_idx, metric, value, …
    """

    def __init__(self, output_dir: "str | Path") -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()

    # ------------------------------------------------------------------ factories

    @classmethod
    def from_output_dir(cls, path: "str | Path") -> "ExperimentResults":
        """Create from an explicit filesystem path."""
        return cls(path)

    @classmethod
    def from_experiment_name(
        cls,
        name: str,
        labs_root: Optional[Path] = None,
    ) -> "ExperimentResults":
        """Locate the output directory by experiment name.

        Searches under ``labs_root()/<name>`` first (flat), then
        ``labs_root()/*/<name>`` (nested lab).

        Parameters
        ----------
        name:
            Experiment name as written in ``experiment.yaml``.
        labs_root:
            Override the default ``labs_root()/`` root.
        """
        from mas.lab.paths import labs_root as _labs_root_fn
        root = labs_root or _labs_root_fn()

        # flat: labs_root()/<name>/
        direct = root / name
        if direct.is_dir():
            return cls(direct)

        # nested: labs_root()/<lab>/<name>/
        for candidate in root.iterdir():
            if candidate.is_dir():
                nested = candidate / name
                if nested.is_dir():
                    return cls(nested)

        raise FileNotFoundError(
            f"Experiment output {name!r} not found under {root}"
        )

    # ------------------------------------------------------------------ hierarchy

    @property
    def scenarios(self) -> List[ScenarioView]:
        """All scenario directories, sorted alphabetically.

        A directory is considered a scenario if it is not hidden (does not
        start with ``"."``) and contains at least one ``item*`` sub-directory.
        This structural check avoids treating pipeline artefact directories
        (``plots/``, ``.cache/``, ``results/`` …) as scenarios.
        """
        views = []
        for d in self.output_dir.iterdir():
            if not d.is_dir():
                continue
            if d.name.startswith("."):
                continue
            if d.name in _SKIP_NAMES:
                continue
            # Structural guard: only dirs that contain item* children.
            if any(_ITEM_RE.match(child.name) for child in d.iterdir() if child.is_dir()):
                views.append(ScenarioView(d))
        return sorted(views, key=lambda s: s.scenario_id)

    # ------------------------------------------------------------------ fan-in

    def collect_dataframe(
        self,
        filename: str,
        flatten: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fan-in per-run files into an experiment-level tidy DataFrame.

        Reads *filename* from every run across all scenarios and items,
        annotates each row with its origin (``scenario``, ``item_id``,
        ``run_idx``), and concatenates everything into a single DataFrame.

        Parameters
        ----------
        filename:
            JSON file to read from each run directory (e.g.
            ``"metrics.json"``).
        flatten:
            If given, expand ``data[flatten]`` into one row per nested key
            (see :meth:`RunView.load_dataframe`).

        Returns
        -------
        pd.DataFrame
            Tidy DataFrame with identity columns prepended:
            ``scenario``, ``item_id``, ``run_idx``, then all columns
            from the per-run DataFrames.
        """
        frames: list[pd.DataFrame] = []

        for scenario in self.scenarios:
            for item in scenario.items:
                for run in item.runs:
                    df = run.load_dataframe(filename, flatten=flatten)
                    if df.empty:
                        continue
                    df.insert(0, "run_idx", int(run.run_id))
                    df.insert(0, "item_id", item.item_id)
                    df.insert(0, "scenario", scenario.scenario_id)
                    frames.append(df)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def __repr__(self) -> str:
        return f"ExperimentResults({str(self.output_dir)!r})"
