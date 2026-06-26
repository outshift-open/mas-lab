#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Letta wrapper — thin adapter around upstream Letta Block/Memory classes.

Integration mode: **wrapper** — delegates to ``letta.schemas.block.Block``
and ``letta.schemas.memory.BasicBlockMemory`` from the upstream ``letta``
package.  All block operations (append, replace, rethink) are performed by
Letta's own code; this adapter translates between MAS ``ContextContract``
and Letta's API.

Dependencies
------------
Requires the ``letta`` package (see ``labs/extensions.lab/README.md``)::

    uv sync --group labs-full
    # or: pip install 'mas-lab[extensions]'
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mas.runtime.contracts.context_contract import (
    ContextContract,
    ContextPart,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports to avoid hard dependency
# ---------------------------------------------------------------------------
_letta_block_cls = None
_letta_memory_cls = None


def _ensure_letta():
    """Lazy import letta Block and BasicBlockMemory."""
    global _letta_block_cls, _letta_memory_cls
    if _letta_block_cls is not None:
        return
    try:
        from letta.schemas.block import Block
        from letta.schemas.memory import BasicBlockMemory
        _letta_block_cls = Block
        _letta_memory_cls = BasicBlockMemory
    except ImportError as exc:
        raise ImportError(
            "letta is required for LettaCoreMemoryWrapper. "
            "Install with: uv sync --group labs-full  "
            "or pip install 'mas-lab[extensions]'"
        ) from exc


class LettaCoreMemoryWrapper(ContextContract):
    """Thin wrapper around Letta's Block/BasicBlockMemory.

    Delegates all block storage and manipulation to upstream Letta classes.
    Renders blocks into the context window via ``collect_context()``.

    Parameters
    ----------
    blocks:
        Initial block definitions.  Each dict maps to a Letta ``Block``.
    """

    plugin_id = "letta_core_memory_wrapper@v1"

    def __init__(self, blocks: Optional[List[Dict[str, Any]]] = None):
        _ensure_letta()

        block_objs = []
        for bdef in (blocks or []):
            block_objs.append(_letta_block_cls(
                label=bdef["label"],
                value=bdef.get("value", ""),
                limit=bdef.get("limit", 8000),
                description=bdef.get("description"),
                read_only=bdef.get("read_only", False),
            ))
        if not block_objs:
            block_objs = [
                _letta_block_cls(label="persona", value="", limit=8000),
                _letta_block_cls(label="human", value="", limit=8000),
            ]

        self._memory = _letta_memory_cls(blocks=block_objs)

    def get_block(self, label: str):
        block = self._memory.get_block(label)
        if block is None:
            labels = [b.label for b in self._memory.get_blocks()]
            raise KeyError(f"No memory block '{label}'. Available: {labels}")
        return block

    def list_blocks(self):
        return self._memory.get_blocks()

    @property
    def letta_memory(self):
        return self._memory

    def collect_context(self, request: Optional[Any] = None) -> List[ContextPart]:
        blocks = self._memory.get_blocks()
        if not blocks:
            return []

        lines = ["<memory_blocks>"]
        for block in blocks:
            label = block.label or "unnamed"
            chars = len(block.value) if block.value else 0
            lines.append(f"  <{label}>")
            lines.append(
                f"    <metadata>chars_current={chars}, "
                f"chars_limit={block.limit}, "
                f"read_only={block.read_only}</metadata>"
            )
            lines.append(f"    <value>{block.value or ''}</value>")
            lines.append(f"  </{label}>")
        lines.append("</memory_blocks>")

        return [ContextPart.memory("\n".join(lines))]
