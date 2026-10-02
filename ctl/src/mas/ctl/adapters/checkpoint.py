#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Checkpoint persistence — session snapshots above the kernel."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class CheckpointStore(Protocol):
    def save(self, snapshot: dict, *, label: str = "") -> Path: ...

    def load(self, path: Path) -> dict: ...

    def list_checkpoints(self) -> list[Path]: ...


@dataclass
class JsonCheckpointStore:
    """File-backed checkpoint store (one JSON file per checkpoint)."""

    directory: Path
    memory_seeds: list[dict] = field(default_factory=list)
    turn_counter: int = 0

    def __post_init__(self) -> None:
        self.directory = Path(self.directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: dict, *, label: str = "") -> Path:
        self.turn_counter += 1
        name = label or f"turn-{self.turn_counter:04d}"
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
        path = self.directory / f"{safe}.checkpoint.json"
        if snapshot.get("version") == 2:
            payload = dict(snapshot)
        else:
            payload = {
                "version": 1,
                "label": label or name,
                "turn": self.turn_counter,
                "kernel": snapshot,
                "memory_seeds": list(self.memory_seeds),
            }
        _validate_checkpoint_payload(payload)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def load(self, path: Path) -> dict:
        data = self.load_payload(path)
        return data["kernel"]

    def load_payload(self, path: Path) -> dict:
        """Load and return the complete validated checkpoint document."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        _validate_checkpoint_payload(data)
        self.memory_seeds = list(data.get("memory_seeds") or [])
        self.turn_counter = int(data.get("turn", 0))
        return data

    def list_checkpoints(self) -> list[Path]:
        return sorted(self.directory.glob("*.checkpoint.json"))

    def retain(self, session_id: str, mode: str, n: int) -> None:
        """Prune only one session's files, preserving unrelated checkpoints."""
        matching = sorted(
            self.directory.glob(f"{session_id}-*.checkpoint.json"),
            key=lambda path: path.stat().st_mtime_ns,
        )
        keep_count = 1 if mode == "single" else n if mode == "last_n" else len(matching)
        for path in matching[:-keep_count] if keep_count else matching:
            path.unlink()


@dataclass
class InMemoryCheckpointStore:
    """Process-local checkpoint store for backtracking without disk writes."""

    snapshots: dict[Path, dict] = field(default_factory=dict)
    counter: int = 0

    def save(self, snapshot: dict, *, label: str = "") -> Path:
        self.counter += 1
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
        path = Path(f"{safe or 'checkpoint'}-{self.counter:08d}.checkpoint.json")
        _validate_checkpoint_payload(snapshot)
        self.snapshots[path] = deepcopy(snapshot)
        return path

    def load(self, path: Path) -> dict:
        return self.load_payload(path)["kernel"]

    def load_payload(self, path: Path) -> dict:
        try:
            return deepcopy(self.snapshots[Path(path)])
        except KeyError as exc:
            raise FileNotFoundError(path) from exc

    def list_checkpoints(self) -> list[Path]:
        return sorted(self.snapshots)

    def retain(self, session_id: str, mode: str, n: int) -> None:
        matching = sorted(path for path in self.snapshots if path.name.startswith(f"{session_id}-"))
        keep_count = 1 if mode == "single" else n if mode == "last_n" else len(matching)
        for path in matching[:-keep_count] if keep_count else matching:
            del self.snapshots[path]


def _validate_checkpoint_payload(data: dict) -> None:
    from mas.ctl.validate import validate_data, validation_enabled

    if validation_enabled():
        validate_data(data, kind="checkpoint", source="checkpoint.json").raise_if_failed()
