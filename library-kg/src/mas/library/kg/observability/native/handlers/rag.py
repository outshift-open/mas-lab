#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the ``rag_query_start`` / ``rag_query_end`` event kinds (RAGQuery).

RAGQuery has no class-specific enrichment beyond the common call-node
fields (start/end time, status, provenance) that ``upsert_call`` already
populates for every structural kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from mas.library.kg.core.native_graph_builder import NativeGraphBuilder


def handle_rag_query(event: Dict[str, Any], builder: "NativeGraphBuilder") -> List[Dict[str, Any]]:
    node = builder.upsert_call(event, "RAGQuery")
    return [node] if node is not None else []
