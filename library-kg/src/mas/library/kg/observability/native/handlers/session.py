#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the ``mas_call_start`` / ``mas_call_end`` event kinds (MASCall)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from mas.library.kg.core.native_graph_builder import NativeGraphBuilder


def handle_mas_call(event: Dict[str, Any], builder: "NativeGraphBuilder") -> List[Dict[str, Any]]:
    node = builder.upsert_call(event, "MASCall")
    if node is None:
        return []
    kind = event.get("kind", "")
    if kind.endswith("_start"):
        node.setdefault("masName", event.get("mas_name") or event.get("agent_id", ""))
        node.setdefault("masType", event.get("mas_type", ""))
    return [node]
