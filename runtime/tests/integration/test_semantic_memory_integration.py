#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Semantic memory store integration."""

from mas.runtime.boundary.memory.semantic import SemanticMemoryStore


def test_semantic_memory_index_and_search(tmp_path):
    db = tmp_path / "mem.db"
    store = SemanticMemoryStore(db_path=db)
    store.index_document("doc1", "Paris hotels near the river Seine")
    hits = store.search("Paris hotels")
    assert hits
    assert hits[0][0] == "doc1"
    store.close()
