#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Fallback handler for call-tree event kinds with no class-specific
enrichment: ``ParallelGroup`` (parallel_group_start/end), ``Branch``
(branch_start/end), and ``Worker`` (infrastructure_info, when it happens to
carry a call_id). These get the common call-node fields from
``upsert_call`` and nothing else, same as today.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from mas.library.kg.core.native_graph_builder import NativeGraphBuilder


def handle_generic_call(
    event: Dict[str, Any], builder: "NativeGraphBuilder"
) -> List[Dict[str, Any]]:
    local_name = event.get("mas_class", "ExecutionElement")
    node = builder.upsert_call(event, local_name)
    return [node] if node is not None else []
