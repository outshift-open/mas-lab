#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ApplicationRunner protocol — core lab execution contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

try:
    from mas.runtime.run_artifact import RunArtifact
except ImportError:  # pragma: no cover - core stays importable without runtime
    from dataclasses import dataclass as _dc

    @_dc
    class RunArtifact:  # type: ignore[no-redef]
        kind: str = "artifact"
        path: Optional[Path] = None
        stream: bool = False
        meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Typed return value from :meth:`ApplicationRunnerProtocol.run`."""

    content: str
    status: Literal["ok", "error"] = "ok"
    error: Optional[str] = None
    artifacts: List[RunArtifact] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def events_path(self) -> Optional[Path]:
        for artifact in self.artifacts:
            if artifact.kind == "events" and artifact.path:
                return artifact.path
        return None

    @property
    def stats_paths(self) -> List[Path]:
        return [a.path for a in self.artifacts if a.kind == "sys_stats" and a.path]

    def artifact(self, kind: str) -> Optional[RunArtifact]:
        for artifact in self.artifacts:
            if artifact.kind == kind:
                return artifact
        return None


class ApplicationRunnerProtocol(ABC):
    """Execute one application/agent prompt and return artifacts."""

    runner_id: str

    @abstractmethod
    def run(
        self,
        prompt: str,
        *,
        config: Dict[str, Any],
        spec_path: Path,
        flavour: Any,
        output_dir: Path,
        turns: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        memory_seeds: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> RunResult:
        ...

    @abstractmethod
    def supports_contract(self, contract_id: str) -> bool:
        ...

    def get_supported_contracts(self) -> List[str]:
        return []
