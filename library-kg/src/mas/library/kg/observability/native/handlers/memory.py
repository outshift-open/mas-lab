#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the ``memory_call_*`` / ``memory_store_*`` / ``memory_retrieve_*``
event kinds (MemoryCall).

MemoryCall has no class-specific enrichment beyond the common call-node
fields that ``upsert_call`` already populates for every structural kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from mas.library.kg.core.native_graph_builder import NativeGraphBuilder


def handle_memory_call(
    event: Dict[str, Any], builder: "NativeGraphBuilder"
) -> List[Dict[str, Any]]:
    node = builder.upsert_call(event, "MemoryCall")
    return [node] if node is not None else []
