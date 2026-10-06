#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Generic KG node annotation.

``annotate_kg_nodes`` is the primary API. It adds computed annotation nodes
and edges to a KG document for any node type, driven by a caller-supplied
``value_fn``.

The caller provides the external computation (embedding, scoring, labelling,
etc.); this module only manages graph structure.

Example — embed State nodes via OpenAI::

    from mas.library.kg.core.annotate import annotate_kg_nodes
    import openai

    client = openai.OpenAI()

    def embed_fn(node):
        content = node.get("content", "").strip()
        if not content:
            return None
        resp = client.embeddings.create(
            model="text-embedding-3-small", input=[content]
        )
        return {
            "vector": resp.data[0].embedding,
            "model": "text-embedding-3-small",
            "dimensions": 1536,
        }

    enriched = annotate_kg_nodes(
        doc,
        node_type="State",
        edge_name="hasEmbedding",
        value_fn=embed_fn,
        annotation_node_type="StateEmbedding",
    )
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable, Dict, List, Optional

__all__ = ["annotate_kg_nodes"]


def annotate_kg_nodes(
    doc: Dict[str, Any],
    *,
    node_type: str,
    edge_name: str,
    value_fn: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    annotation_node_type: str = "Annotation",
    id_prefix: str = "urn:mas:annotation:",
) -> Dict[str, Any]:
    """Add computed annotation nodes and edges to a KG document.

    For each node where ``node["node_type"] == node_type``, calls
    ``value_fn(node)``.  If it returns a dict, adds:

    * A new node with ``node_type=annotation_node_type`` and the returned
      fields merged in.
    * An edge of type ``edge_name`` from the source node → annotation node.

    If ``value_fn`` returns ``None``, the node is skipped.

    The input document is **not mutated**. When at least one annotation is
    added, a new document dict is returned. When ``value_fn`` matches no
    node (nothing to add), the exact same ``doc`` object is returned —
    callers that need a fresh dict unconditionally should copy it
    themselves (``dict(result)``).

    Args:
        doc: KG document dict (``{"nodes": [...], "edges": [...], ...}``).
        node_type: Filter — only annotate nodes where
            ``node["node_type"] == node_type``.
        edge_name: Edge type to add (e.g. ``"hasEmbedding"``).
        value_fn: Called with each matching node dict.  Return a dict of
            fields for the annotation node, or ``None`` to skip.
        annotation_node_type: ``node_type`` value for the new annotation nodes.
            Default: ``"Annotation"``.
        id_prefix: Prefix for generated annotation node IDs.

    Returns:
        New KG document dict with additional annotation nodes + edges.

    Raises:
        TypeError: if ``value_fn`` returns something other than dict or None.
    """
    new_nodes: List[Dict[str, Any]] = []
    new_edges: List[Dict[str, Any]] = []

    existing_nodes: List[Dict[str, Any]] = doc.get("nodes") or []
    existing_edges: List[Dict[str, Any]] = doc.get("edges") or []

    for node in existing_nodes:
        if str(node.get("node_type") or "") != node_type:
            continue

        annotation_fields = value_fn(node)
        if annotation_fields is None:
            continue
        if not isinstance(annotation_fields, dict):
            raise TypeError(f"value_fn must return dict or None; got {type(annotation_fields)}")

        source_id: str = node.get("id") or str(uuid.uuid4())

        # Stable annotation ID: deterministic from source node id + edge name
        content_hash = hashlib.sha256(
            json.dumps({"source": source_id, "edge": edge_name}, sort_keys=True).encode()
        ).hexdigest()[:16]
        annotation_id = f"{id_prefix}{content_hash}"

        annotation_node: Dict[str, Any] = {
            "id": annotation_id,
            "node_type": annotation_node_type,
            "source_node_id": source_id,
            **annotation_fields,
        }
        new_nodes.append(annotation_node)
        new_edges.append(
            {
                "from_id":   source_id,
                "to_id":     annotation_id,
                "source":    source_id,
                "target":    annotation_id,
                "edge_type": edge_name,
            }
        )

    if not new_nodes:
        return doc  # nothing added — same object back (see docstring: not copied in this case)

    result = dict(doc)
    result["nodes"] = list(existing_nodes) + new_nodes
    result["edges"] = list(existing_edges) + new_edges
    return result
