#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Run-level artifact value object.

A :class:`RunArtifact` represents a single output produced by one agent
execution (``SessionController`` / ``RuntimeKernel``).  It is intentionally minimal and
has zero dependencies outside the standard library so that it can be imported
by both ``mas.runtime`` and ``mas.lab`` layers without creating circular imports.

Artifact kinds
--------------
``"events"``
    The primary JSONL telemetry stream — ``traces/events.jsonl``.
    Always stream-backed; optionally also a file artifact.
``"sys_stats"``
    The aggregated :class:`~mas.runtime.stats_registry.StatsRegistry` snapshot.
    Written as ``traces/stats-<agent_id>.json`` (file sink) and embedded as a
    ``sys_stats`` event in the events stream (stream sink).
``"ui_feed"``
    The live UI feed — ``logs/ui_feed.jsonl``.

Any runner may produce additional kinds by using arbitrary strings (e.g.
``"langgraph_trace"``, ``"crewai_events"``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


#: Modes in which an artifact is materialised.
FILE_SINK   = "file"    # written to a file on disk
STREAM_SINK = "stream"  # appended to the events.jsonl stream


@dataclass
class RunArtifact:
    """A single output artifact produced by one agent / MAS run.

    Parameters
    ----------
    kind:
        Canonical artifact type name (``"events"``, ``"sys_stats"``, …).
    path:
        Absolute path to the file on disk.  ``None`` for pure in-memory
        or stream-only artifacts.
    stream:
        True if this artifact is also emitted live to the events.jsonl
        stream as a ``kind``-typed event.
    data:
        In-memory payload — used when the artifact has not been (or should
        not be) serialised to disk, e.g. for pass-through between pipeline
        steps within the same process.
    meta:
        Arbitrary provenance metadata (agent_id, run_id, model, …).
    """

    kind:   str
    path:   Optional[Path]           = None
    stream: bool                     = False
    data:   Any                      = None
    meta:   Dict[str, Any]           = field(default_factory=dict)

    # -- convenience ----------------------------------------------------------

    def is_file(self) -> bool:
        """True iff ``path`` points to an existing file."""
        return self.path is not None and Path(self.path).exists()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind":   self.kind,
            "path":   str(self.path) if self.path else None,
            "stream": self.stream,
            "meta":   self.meta,
        }

    def __repr__(self) -> str:
        loc = f"path={self.path}" if self.path else "in-memory"
        return f"<RunArtifact kind={self.kind!r} {loc} stream={self.stream}>"


def make_events_artifact(run_output_dir: Path, agent_id: str = "") -> RunArtifact:
    """Build the standard ``events`` artifact pointing to events.jsonl."""
    return RunArtifact(
        kind="events",
        path=run_output_dir / "traces" / "events.jsonl",
        stream=True,  # EventRecorder writes live to this file
        meta={"agent_id": agent_id},
    )


def make_stats_artifact(run_output_dir: Path, agent_id: str) -> RunArtifact:
    """Build the ``sys_stats`` artifact pointing to stats-<agent_id>.json."""
    return RunArtifact(
        kind="sys_stats",
        path=run_output_dir / "traces" / f"stats-{agent_id}.json",
        stream=True,  # also emitted as sys_stats event in events.jsonl
        meta={"agent_id": agent_id},
    )
