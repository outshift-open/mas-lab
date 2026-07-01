#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Memory seeds — preload context before first turn (TLA M_mem + manifest parity)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mas.runtime.driver.instance import RuntimeInstance

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemorySeed:
    key: str
    content: str


class MemorySeedLoader:
    @staticmethod
    def load_path(path: Path) -> list[MemorySeed]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return MemorySeedLoader.load_data(raw)

    @staticmethod
    def load_data(raw: Any) -> list[MemorySeed]:
        if raw is None:
            return []
        if isinstance(raw, list):
            entries = raw
        elif isinstance(raw, dict):
            entries = raw.get("entries") or raw.get("seeds") or raw.get("spec", {}).get("entries", [])
        else:
            return []
        out: list[MemorySeed] = []
        for entry in entries:
            if isinstance(entry, dict):
                key = str(
                    entry.get("key")
                    or entry.get("id")
                    or entry.get("source")
                    or "seed"
                )
                content = str(entry.get("content") or entry.get("text") or "")
                if content:
                    out.append(MemorySeed(key=key, content=content))
        return out


def seeds_from_manifest(manifest: dict) -> list[MemorySeed]:
    """Extract inline spec.memory_seed entries from a merged Agent manifest."""
    spec = manifest.get("spec") or {}
    raw = spec.get("memory_seed") or []
    if not isinstance(raw, list):
        return []
    return MemorySeedLoader.load_data(raw)


def apply_memory_seeds(instance: RuntimeInstance, seeds: list[MemorySeed]) -> None:
    """Inject seeds into ctx assembler — visible on next CTX assembly."""
    ctx = instance.driver.ctx
    if ctx is None:
        return
    if hasattr(ctx, "memory_seeds"):
        ctx.memory_seeds.extend([(s.key, s.content) for s in seeds])


def index_seeds_in_semantic_memory(
    seeds: list[MemorySeed],
    *,
    agent_id: str = "default",
    db_path: str | None = None,
) -> None:
    """Index memory_seed entries into SemanticMemoryPlugin's SQLite store."""
    if not seeds:
        return
    try:
        from mas.library.standard.plugins.memory.memory_semantic import SemanticMemoryPlugin
        from mas.runtime.boundary.memory.semantic import default_store_path
    except ImportError:
        logger.debug("SemanticMemoryPlugin unavailable — skipping seed indexing")
        return

    resolved = db_path or str(default_store_path(agent_id))
    mem = SemanticMemoryPlugin(db_path=resolved, context_inject=False)
    mem.agent_id = agent_id
    for seed in seeds:
        payload: dict[str, Any] = {
            "content": seed.content,
            "source": seed.key,
        }
        if seed.key:
            payload["key"] = seed.key
        mem.write_memory("semantic", payload)
    mem.close()
