#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Discover run artifacts on disk for pipeline steps and golden tests."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from mas.lab.runners.protocol import RunArtifact, RunResult

_DEFAULT_EVENT_GLOBS = (
    "traces/events.jsonl",
    "**/traces/events.jsonl",
    "events.jsonl",
)


class ArtifactCollector:
    """Collect typed artifacts under a run output directory."""

    @staticmethod
    def discover(output_dir: Path) -> List[RunArtifact]:
        if not output_dir.is_dir():
            return []

        artifacts: List[RunArtifact] = []
        seen: set[str] = set()

        def _add(kind: str, path: Path, *, stream: bool = False) -> None:
            key = f"{kind}:{path.resolve()}"
            if key in seen or not path.is_file():
                return
            seen.add(key)
            artifacts.append(
                RunArtifact(kind=kind, path=path, stream=stream, meta={"source": "collector"})
            )

        for pattern in _DEFAULT_EVENT_GLOBS:
            for path in sorted(output_dir.glob(pattern)):
                _add("events", path)

        otel_dir = output_dir / "otel"
        if otel_dir.is_dir():
            for path in sorted(otel_dir.rglob("*")):
                if path.is_file():
                    _add("otel", path)

        for name in ("metrics.json", "run_info.json", "result.json"):
            candidate = output_dir / name
            _add("metrics" if name == "metrics.json" else "run_meta", candidate)

        stats = output_dir / "sys_stats.json"
        _add("sys_stats", stats)

        return artifacts

    @staticmethod
    def enrich(result: RunResult, output_dir: Path) -> RunResult:
        """Merge discovered files into *result* without duplicating kinds."""
        present = {a.kind for a in result.artifacts if a.path}
        for artifact in ArtifactCollector.discover(output_dir):
            if artifact.kind in present and artifact.kind == "events":
                continue
            if artifact.kind not in present:
                result.artifacts.append(artifact)
                present.add(artifact.kind)
        return result

    @staticmethod
    def first_events_path(output_dir: Path) -> Optional[Path]:
        for artifact in ArtifactCollector.discover(output_dir):
            if artifact.kind == "events" and artifact.path:
                return artifact.path
        return None

    @staticmethod
    def read_tail(path: Path, *, max_lines: int = 50) -> Iterable[str]:
        if not path.is_file():
            return []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return lines[-max_lines:]
