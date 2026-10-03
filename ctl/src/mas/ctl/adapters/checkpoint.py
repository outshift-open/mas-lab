#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Checkpoint persistence — session snapshots above the kernel.

Implementations are library ``checkpoint_store`` plugins. This module
re-exports them so ctl callers keep a stable import path.
"""

from __future__ import annotations

from pathlib import Path

from mas.library.standard.plugins.checkpoint import (
    HybridCheckpointStore,
    InMemoryCheckpointStore,
    JsonCheckpointStore,
    _validate_checkpoint_payload,
    instantiate_store,
)
from mas.runtime.session.state import CheckpointStore
from mas.runtime.spec.checkpoint import CheckpointPolicy

__all__ = [
    "CheckpointStore",
    "HybridCheckpointStore",
    "InMemoryCheckpointStore",
    "JsonCheckpointStore",
    "build_checkpoint_store",
    "_validate_checkpoint_payload",
]


def build_checkpoint_store(
    policy: CheckpointPolicy,
    directory: Path | None,
) -> JsonCheckpointStore | InMemoryCheckpointStore | HybridCheckpointStore | None:
    """Resolve ``spec.checkpoint.storage`` through the checkpoint_store plugin type."""
    kind = policy.resolved_storage()
    if kind == "none":
        if directory is None:
            return None
        kind = "disk"
    try:
        return instantiate_store(kind, directory)
    except ValueError:
        if kind == "memory":
            return InMemoryCheckpointStore()
        if directory is None:
            raise
        if kind == "hybrid":
            return HybridCheckpointStore(directory)
        return JsonCheckpointStore(directory)
