#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Protocol adapters — stdin/REST/WS terminators producing Σ_in."""

from mas.ctl.adapters.checkpoint import CheckpointStore, JsonCheckpointStore
from mas.ctl.adapters.hitl_terminal import HitlTerminal, ScriptedHitlTerminal
from mas.ctl.adapters.memory_seed import MemorySeed, MemorySeedLoader, apply_memory_seeds

__all__ = [
    "CheckpointStore",
    "HitlTerminal",
    "JsonCheckpointStore",
    "MemorySeed",
    "MemorySeedLoader",
    "ScriptedHitlTerminal",
    "apply_memory_seeds",
]
