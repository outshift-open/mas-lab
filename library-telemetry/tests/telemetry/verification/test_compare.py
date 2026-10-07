#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Span parity comparison tests — pure (no OTel SDK required)."""

from __future__ import annotations

from mas.library.telemetry.verification import compare_otel_span_sets


def _span(name, sid, tid, parent=None, extra=None):
    a = {"mas.boundary": name}
    if extra:
        a.update(extra)
    return {
        "name": name,
        "context": {"span_id": sid, "trace_id": tid},
        "parent_id": parent,
        "attributes": a,
    }


def _tree(tid, prefix):
    # TaskCall → AgentCall → (LLMCall, ToolCall)
    return [
        _span("TaskCall", f"{prefix}0", tid),
        _span(
            "AgentCall",
            f"{prefix}1",
            tid,
            parent=f"{prefix}0",
            extra={"mas.agent.id": "p"},
        ),
        _span(
            "LLMCall",
            f"{prefix}2",
            tid,
            parent=f"{prefix}1",
            extra={"mas.llm.model": "gpt-4o"},
        ),
        _span(
            "ToolCall",
            f"{prefix}3",
            tid,
            parent=f"{prefix}1",
            extra={"mas.tool.name": "search"},
        ),
    ]


def test_identical_semantics_pass_despite_different_ids():
    ref = _tree("trace-A", "a")
    cand = _tree("trace-B", "b")  # different ids, same semantics/topology
    report = compare_otel_span_sets(ref, cand)
    assert report["passed"], report["checks"]
    assert report["summary"]["failed"] == 0


def test_missing_span_fails_count_and_topology():
    ref = _tree("t", "a")
    cand = ref[:-1]  # drop the ToolCall
    report = compare_otel_span_sets(ref, cand)
    assert not report["passed"]
    failed = {c["check"] for c in report["checks"] if not c["passed"]}
    assert "span_count" in failed
    assert "span_name_counts" in failed


def test_changed_attr_value_fails_values_only():
    ref = _tree("t", "a")
    cand = _tree("t", "a")
    cand[2]["attributes"]["mas.llm.model"] = "different-model"
    report = compare_otel_span_sets(ref, cand)
    failed = {c["check"] for c in report["checks"] if not c["passed"]}
    assert "mas_attr_values" in failed
    assert "span_count" not in failed  # counts/topology still match
