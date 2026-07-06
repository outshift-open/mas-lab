#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Typed artifact value objects for the mas-lab processor/pipeline system.

Artifacts are the strongly-typed values that flow between :class:`Processor`
instances and pipeline steps.  Every artifact has:

* a ``kind`` class-variable — the canonical type name used in YAML / CLI
* an optional ``path`` — when the artifact is disk-backed (file)
* an optional ``data`` — when the artifact is in-memory only
* a ``meta`` dict — provenance, run_id, timestamps, …

Hierarchy::

    Artifact
    ├── Trajectory               ← raw JSONL event trace
    │   └── AnnotatedTrajectory  ← + highlights + analyst notes
    ├── PlotFile                 ← rendered HTML / SVG / PNG
    ├── NormalizedTrace          ← normalized manifold trace (JSONL)
    └── KnowledgeGraph           ← JSON-LD graph file
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass
class Artifact:
    """Base value object for all typed artifacts.

    Parameters
    ----------
    path:
        File path when the artifact lives on disk.
    data:
        In-memory payload (list, dict, str, …) when the artifact is not
        backed by a file, or has already been loaded from one.
    meta:
        Arbitrary provenance metadata (run_id, timestamps, labels …).
    """

    kind: ClassVar[str] = "artifact"

    path: Optional[Path] = None
    data: Any = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def is_file(self) -> bool:
        """True iff ``path`` points to an existing file."""
        return self.path is not None and Path(self.path).exists()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path) if self.path else None,
            "meta": self.meta,
        }

    def __repr__(self) -> str:
        loc = f"path={self.path}" if self.path else "in-memory"
        return f"<{self.__class__.__name__} {loc}>"


# ---------------------------------------------------------------------------
# Trajectory family
# ---------------------------------------------------------------------------

@dataclass
class Trajectory(Artifact):
    """Raw MAS execution trace — a list of OTEL-style event dicts.

    The ``events`` list is populated lazily: calling :meth:`load` reads the
    JSONL file at ``path`` if ``events`` is empty.
    """

    kind: ClassVar[str] = "trajectory"

    events: List[Dict[str, Any]] = field(default_factory=list)
    run_id: str = ""

    def load(self) -> "Trajectory":
        """Load events from ``path`` (or ``run_id``) into ``events`` (idempotent)."""
        if not self.events:
            source = self.path or (self.run_id or None)
            if source:
                from mas.lab.plots.trajectory import load_trace  # lazy import
                self.events = load_trace(source)
        return self

    def as_dict(self) -> Dict[str, Any]:
        d = super().as_dict()
        d["run_id"] = self.run_id
        return d


@dataclass
class AnnotatedTrajectory(Trajectory):
    """Trajectory enriched with analyst highlights and free-form notes.

    Parameters
    ----------
    highlights:
        Each entry is a correlation-id prefix (e.g. ``"f19445b6"``) **or** a
        1-based delegation index (e.g. ``"3"``).
    notes:
        List of ``{"index": int, "note": str}`` dicts — one per highlighted
        delegation.  Rendered as tooltips or annotations in plots.
    """

    kind: ClassVar[str] = "annotated_trajectory"

    highlights: List[str] = field(default_factory=list)
    notes: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        d = super().as_dict()
        d["highlights"] = self.highlights
        d["notes"] = self.notes
        return d


# ---------------------------------------------------------------------------
# Plot artifacts
# ---------------------------------------------------------------------------

@dataclass
class PlotFile(Artifact):
    """A rendered visualisation written to disk (HTML, SVG, PNG …)."""

    kind: ClassVar[str] = "plot_file"

    format: str = "html"
    """One of: html, svg, mermaid, png."""

    def as_dict(self) -> Dict[str, Any]:
        d = super().as_dict()
        d["format"] = self.format
        return d


# ---------------------------------------------------------------------------
# Knowledge-graph family
# ---------------------------------------------------------------------------

@dataclass
class NormalizedTrace(Artifact):
    """Normalized manifold trace (JSONL) ready for KG construction."""

    kind: ClassVar[str] = "normalized_trace"

    run_id: str = ""

    def as_dict(self) -> Dict[str, Any]:
        d = super().as_dict()
        d["run_id"] = self.run_id
        return d


@dataclass
class KnowledgeGraph(Artifact):
    """JSON-LD knowledge graph produced by the manifold normalizer."""

    kind: ClassVar[str] = "knowledge_graph"

    run_id: str = ""

    def load_json(self) -> Any:
        """Read and return the JSON-LD dict from ``path``."""
        if self.path:
            return json.loads(Path(self.path).read_text(encoding="utf-8"))
        return self.data

    def as_dict(self) -> Dict[str, Any]:
        d = super().as_dict()
        d["run_id"] = self.run_id
        return d


# ---------------------------------------------------------------------------
# MCE session-metrics artefacts
# ---------------------------------------------------------------------------

@dataclass
class SessionMetrics(Artifact):
    """MCE metric scores for one MAS session.

    Written as ``metrics.json`` next to ``run_info.json`` in each run folder
    (``item{N}/r{K}/metrics.json``) by :class:`EvalMceBatchStep`.

    Parameters
    ----------
    item_id:
        Dataset item identifier (e.g. ``"1"``).
    scenario:
        Benchmark scenario name (e.g. ``"baseline"``).
    session:
        Session-level scores keyed by metric_id.
        Each value is ``{"value": float|None, "reasoning": str, "error": str|None}``.
    agents:
        Per-agent scores (empty in schema_version="1").
        Reserved for future extension.
    schema_version:
        Artefact format version.  Increment on breaking changes.
    """

    kind: ClassVar[str] = "session_metrics"

    item_id:        str = ""
    scenario:       str = ""
    session:        Dict[str, Any] = field(default_factory=dict)
    agents:         Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1"

    def as_dict(self) -> Dict[str, Any]:
        d = super().as_dict()
        d.update({
            "schema_version": self.schema_version,
            "item_id":  self.item_id,
            "scenario": self.scenario,
            "session":  self.session,
            "agents":   self.agents,
        })
        return d

    @classmethod
    def from_json(cls, path: Path) -> "SessionMetrics":
        """Load a ``metrics.json`` file from *path*."""
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            path=path,
            item_id=doc.get("item_id", ""),
            scenario=doc.get("scenario", ""),
            session=doc.get("session", {}),
            agents=doc.get("agents", {}),
            schema_version=doc.get("schema_version", "1"),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ARTIFACT_REGISTRY: Dict[str, Type[Artifact]] = {
    "artifact":              Artifact,
    "trajectory":            Trajectory,
    "annotated_trajectory":  AnnotatedTrajectory,
    "plot_file":             PlotFile,
    "normalized_trace":      NormalizedTrace,
    "knowledge_graph":       KnowledgeGraph,
    "session_metrics":       SessionMetrics,
}


def register_artifact(cls: Type[Artifact]) -> Type[Artifact]:
    """Class decorator — register a custom Artifact subclass by its ``kind``."""
    _ARTIFACT_REGISTRY[cls.kind] = cls
    return cls


def artifact_from_dict(d: Dict[str, Any]) -> Artifact:
    """Reconstruct an Artifact from a dict produced by :meth:`Artifact.as_dict`."""
    cls = _ARTIFACT_REGISTRY.get(d.get("kind", "artifact"), Artifact)
    path = Path(d["path"]) if d.get("path") else None
    inst = cls.__new__(cls)
    # call dataclass __init__ with just the base fields; subclass extras default
    Artifact.__init__(inst, path=path, meta=d.get("meta", {}))
    if hasattr(inst, "run_id") and "run_id" in d:
        inst.run_id = d["run_id"]
    if hasattr(inst, "highlights") and "highlights" in d:
        inst.highlights = d["highlights"]
    if hasattr(inst, "notes") and "notes" in d:
        inst.notes = d["notes"]
    if hasattr(inst, "format") and "format" in d:
        inst.format = d["format"]
    return inst


# ---------------------------------------------------------------------------
# File-level artifact type registry (CLI / show helpers)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileArtifactType:
    """Descriptor for a file-based artifact type."""

    abbrev: str
    label: str
    description: str
    extensions: tuple[str, ...] = ()
    exact_names: tuple[str, ...] = ()
    produced_by: tuple[str, ...] = ()


FILE_ARTIFACT_TYPES: list[FileArtifactType] = [
    FileArtifactType(
        abbrev="CSV",
        label="Tabular results (CSV)",
        description="Comma-separated values table aggregating per-run metrics across all scenarios and items.",
        exact_names=("results.csv",),
        produced_by=("collect_metrics",),
    ),
    FileArtifactType(
        abbrev="CSV",
        label="Tabular data (CSV)",
        description="Comma-separated values table.",
        extensions=("csv",),
        produced_by=("collect_metrics", "to_dataframe", "join_dataframe"),
    ),
    FileArtifactType(
        abbrev="PNG",
        label="Figure (PNG)",
        description="Raster plot image rendered by the pipeline figure step.",
        extensions=("png",),
        produced_by=("plotnine", "metrics_comparison_plot"),
    ),
    FileArtifactType(
        abbrev="SVG",
        label="Figure (SVG)",
        description="Vector plot image rendered by the pipeline figure step.",
        extensions=("svg",),
        produced_by=("plotnine",),
    ),
    FileArtifactType(
        abbrev="HTML",
        label="Interactive report (HTML)",
        description="Browser-viewable interactive visualisation or report.",
        extensions=("html",),
        produced_by=(
            "multilevel_trajectory_plotter",
            "multilevel_trajectory_kg_plotter",
            "plot_multilevel_trajectory",
            "plot_multilevel_trajectory_kg",
        ),
    ),
    FileArtifactType(
        abbrev="KG",
        label="Knowledge graph (JSON)",
        description="Normalized MAS knowledge graph for a single run.",
        exact_names=("kg.json", "kg_otel.json"),
        produced_by=("normalize_events", "normalize_otel"),
    ),
    FileArtifactType(
        abbrev="TrajNative",
        label="Native trajectory plot (HTML)",
        description="Multilevel trajectory rendered from native events.jsonl.",
        exact_names=("trajectory-native.html",),
        produced_by=("plot_multilevel_trajectory", "multilevel_trajectory_plotter"),
    ),
    FileArtifactType(
        abbrev="TrajKG",
        label="KG trajectory plot (HTML)",
        description="Multilevel trajectory rendered from normalized kg.json.",
        exact_names=("trajectory-kg.html",),
        produced_by=("plot_multilevel_trajectory_kg", "multilevel_trajectory_kg_plotter"),
    ),
    FileArtifactType(
        abbrev="Validation",
        label="KG validation report (JSON)",
        description="Structural KG verification results for a single run.",
        exact_names=("validation_report.json",),
        produced_by=("validate_kg",),
    ),
    FileArtifactType(
        abbrev="Parity",
        label="KG parity report (JSON)",
        description="Native vs OTel KG structural comparison for a single run.",
        exact_names=("parity_report.json",),
        produced_by=("compare_kg",),
    ),
    FileArtifactType(
        abbrev="OtelReplay",
        label="OTel replay spans (JSONL)",
        description="OTel SDK spans produced by offline events.jsonl replay.",
        exact_names=("otel_sdk_spans_replay.jsonl",),
        produced_by=("events_to_otel",),
    ),
    FileArtifactType(
        abbrev="Metrics",
        label="Session metrics (JSON)",
        description="Per-run metric scores written by the eval step (metrics.json).",
        exact_names=("metrics.json",),
        produced_by=("eval_mce", "eval_mce_batch", "eval_batch"),
    ),
    FileArtifactType(
        abbrev="RunInfo",
        label="Run info (JSON)",
        description="Execution metadata for a single MAS run (scenario, item, overlays, run hash).",
        exact_names=("run_info.json",),
        produced_by=("mas_runtime",),
    ),
    FileArtifactType(
        abbrev="JSON",
        label="JSON data",
        description="Structured JSON data file.",
        extensions=("json",),
        produced_by=(),
    ),
    FileArtifactType(
        abbrev="SpanSet",
        label="Span set (JSONL)",
        description="Newline-delimited JSON event/span log from a MAS execution trace.",
        extensions=("jsonl",),
        produced_by=("normalize_events", "normalize_otel", "normalize_observe"),
    ),
    FileArtifactType(
        abbrev="FP",
        label="Pipeline fingerprint",
        description="Content hash of a pipeline step's inputs/outputs used for incremental execution.",
        extensions=("fingerprint",),
        produced_by=(),
    ),
    FileArtifactType(
        abbrev="Ref",
        label="Run reference",
        description="Content-addressed pointer to the trace-cache entry for this run.",
        exact_names=(".run_ref",),
        produced_by=("mas_runtime",),
    ),
]

_BY_EXACT: dict[str, FileArtifactType] = {
    nm: t for t in FILE_ARTIFACT_TYPES for nm in t.exact_names
}
_BY_EXT: dict[str, FileArtifactType] = {}
for _t in FILE_ARTIFACT_TYPES:
    for _ext in _t.extensions:
        _BY_EXT.setdefault(_ext, _t)

_UNKNOWN_TYPE = FileArtifactType(
    abbrev="?",
    label="Unknown",
    description="Unrecognised file type.",
)


def classify_file(path: Path) -> FileArtifactType:
    """Return the :class:`FileArtifactType` for *path*."""
    name = path.name
    if name in _BY_EXACT:
        return _BY_EXACT[name]
    ext = path.suffix.lstrip(".")
    return _BY_EXT.get(ext, _UNKNOWN_TYPE)
