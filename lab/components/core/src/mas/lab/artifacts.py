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
