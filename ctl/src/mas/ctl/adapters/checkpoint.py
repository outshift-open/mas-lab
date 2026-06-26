#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Checkpoint persistence — session snapshots above the kernel."""

from __future__ import annotations

import json
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
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        _validate_checkpoint_payload(data)
        self.memory_seeds = list(data.get("memory_seeds") or [])
        self.turn_counter = int(data.get("turn", 0))
        return data["kernel"]

    def list_checkpoints(self) -> list[Path]:
        return sorted(self.directory.glob("*.checkpoint.json"))


def _validate_checkpoint_payload(data: dict) -> None:
    try:
        from mas.ctl.validate import validate_data, validation_enabled

        if not validation_enabled():
            return
        validate_data(data, kind="checkpoint", source="checkpoint.json").raise_if_failed()
    except (ImportError, ValueError):
        if data.get("version") != 1 or "kernel" not in data:
            raise ValueError("invalid checkpoint payload")
