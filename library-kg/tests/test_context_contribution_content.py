# SPDX-License-Identifier: Apache-2.0
"""Normalizer invariant: ContextContribution must carry content when source has text."""

from __future__ import annotations

from mas.library.kg.pipeline import build_kg_document


def test_context_contribution_content_invariant():
    events = [
        {
            "kind": "context_part_contributed",
            "part_id": "p1",
            "agent_id": "cra",
            "parents": [],
            "content": "Patient unresponsive after near drowning in pool.",
            "retained": True,
            "llm_call_id": "llm-1",
        },
        {
            "kind": "llm_call_start",
            "call_id": "llm-1",
            "agent_id": "cra",
            "timestamp": 1.0,
        },
        {
            "kind": "llm_call_end",
            "call_id": "llm-1",
            "agent_id": "cra",
            "timestamp": 2.0,
            "output": "ok",
        },
    ]
    doc = build_kg_document(events, run_id="test", include_provenance=True)
    cc = [n for n in doc["nodes"] if n.get("node_type") == "ContextContribution"]
    assert cc, "expected ContextContribution node"
    for n in cc:
        if events[0].get("content"):
            assert str(n.get("content") or "").strip(), "CC must carry content"
            assert str(n.get("contentPreview") or "").strip(), "CC must carry contentPreview"
