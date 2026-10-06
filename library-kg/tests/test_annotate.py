#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for mas.library.kg.core.annotate.annotate_kg_nodes."""

from __future__ import annotations

import pytest

from mas.library.kg.core.annotate import annotate_kg_nodes

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_doc(*nodes, edges=None):
    return {"nodes": list(nodes), "edges": list(edges or []), "metadata": {}}


def _state(sid, content="hello"):
    return {"id": sid, "node_type": "State", "content": content}


def _agent(aid):
    return {"id": aid, "node_type": "AgentCall"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnnotateKgNodes:
    def test_adds_annotation_node_and_edge(self):
        doc = _minimal_doc(_state("s1"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"vector": [0.1, 0.2]},
        )
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1
        ann_node = result["nodes"][1]
        assert ann_node["vector"] == [0.1, 0.2]
        assert ann_node["source_node_id"] == "s1"

    def test_edge_type_matches_edge_name(self):
        doc = _minimal_doc(_state("s1"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasScore",
            value_fn=lambda n: {"score": 0.9},
        )
        assert result["edges"][0]["edge_type"] == "hasScore"
        assert result["edges"][0]["source"] == "s1"

    def test_value_fn_returning_none_skips_node(self):
        doc = _minimal_doc(_state("s1", content=""), _state("s2", content="hello"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"v": 1} if n.get("content") else None,
        )
        # only s2 should be annotated
        assert len(result["nodes"]) == 3  # s1, s2, annotation for s2
        assert len(result["edges"]) == 1

    def test_non_matching_node_type_skipped(self):
        doc = _minimal_doc(_agent("a1"), _state("s1"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"v": 1},
        )
        # only s1 annotated
        assert len(result["nodes"]) == 3  # a1, s1, annotation
        assert len(result["edges"]) == 1

    def test_no_matching_nodes_returns_original_doc(self):
        doc = _minimal_doc(_agent("a1"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"v": 1},
        )
        assert result is doc  # unchanged reference

    def test_annotation_node_type_default_is_annotation(self):
        doc = _minimal_doc(_state("s1"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"v": 1},
        )
        assert result["nodes"][1]["node_type"] == "Annotation"

    def test_custom_annotation_node_type(self):
        doc = _minimal_doc(_state("s1"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"v": 1},
            annotation_node_type="StateEmbedding",
        )
        assert result["nodes"][1]["node_type"] == "StateEmbedding"

    def test_annotation_id_is_deterministic(self):
        doc = _minimal_doc(_state("s1"))

        def fn(n):
            return {"v": 1}

        r1 = annotate_kg_nodes(doc, node_type="State", edge_name="hasEmbedding", value_fn=fn)
        r2 = annotate_kg_nodes(doc, node_type="State", edge_name="hasEmbedding", value_fn=fn)
        assert r1["nodes"][1]["id"] == r2["nodes"][1]["id"]

    def test_does_not_mutate_input_doc(self):
        doc = _minimal_doc(_state("s1"))
        original_nodes = list(doc["nodes"])
        annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"v": 1},
        )
        assert doc["nodes"] == original_nodes

    def test_multiple_nodes_all_annotated(self):
        doc = _minimal_doc(_state("s1"), _state("s2"), _state("s3"))
        result = annotate_kg_nodes(
            doc,
            node_type="State",
            edge_name="hasEmbedding",
            value_fn=lambda n: {"v": n["id"]},
        )
        assert len(result["nodes"]) == 6  # 3 original + 3 annotations
        assert len(result["edges"]) == 3

    def test_value_fn_returning_non_dict_raises(self):
        doc = _minimal_doc(_state("s1"))
        with pytest.raises(TypeError, match="dict or None"):
            annotate_kg_nodes(
                doc,
                node_type="State",
                edge_name="hasEmbedding",
                value_fn=lambda n: "not a dict",
            )

    def test_metadata_preserved(self):
        doc = _minimal_doc(_state("s1"))
        doc["metadata"] = {"run_id": "test-run"}
        result = annotate_kg_nodes(
            doc, node_type="State", edge_name="x", value_fn=lambda n: {"v": 1}
        )
        assert result["metadata"]["run_id"] == "test-run"

    def test_existing_edges_preserved(self):
        doc = _minimal_doc(_state("s1"))
        doc["edges"] = [{"edge_type": "contains", "from_id": "a", "to_id": "s1"}]
        result = annotate_kg_nodes(
            doc, node_type="State", edge_name="hasEmbedding", value_fn=lambda n: {"v": 1}
        )
        assert len(result["edges"]) == 2
        assert result["edges"][0]["edge_type"] == "contains"
