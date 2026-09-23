#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Advertised tool semantics bind onto a call; names are not inferred."""

from __future__ import annotations

from types import SimpleNamespace

from mas.runtime.contracts.tool_semantics import (
    advertised_semantics_for,
    bind_tool_semantics,
    bound_tool_semantics,
    existing_attr,
)


def test_bind_requires_concept():
    assert bind_tool_semantics({}, {"name": "x"}) is None
    assert bind_tool_semantics({"op": "read"}, {"query": "q"}) is None


def test_bind_skill_subject_from_named_arg():
    advertised = {"concept": "skill", "op": "activate", "subject_arg": "name"}
    assert bind_tool_semantics(advertised, {"name": "answer-formatting"}) == {
        "concept": "skill",
        "op": "activate",
        "subject": "answer-formatting",
    }


def test_bind_memory_write_tries_subject_args_in_order():
    advertised = {"concept": "memory", "op": "write", "subject_arg": ["content", "query"]}
    assert bind_tool_semantics(advertised, {"query": "likes tea"}) == {
        "concept": "memory",
        "op": "write",
        "subject": "likes tea",
    }
    assert bind_tool_semantics(advertised, {"content": "likes tea", "query": "alias"}) == {
        "concept": "memory",
        "op": "write",
        "subject": "likes tea",
    }


def test_bind_without_subject_keeps_op():
    advertised = {"concept": "memory", "op": "write", "subject_arg": "content"}
    assert bind_tool_semantics(advertised, {}) == {"concept": "memory", "op": "write"}


def test_lookup_uses_advertised_list_not_tool_name():
    engine = SimpleNamespace(
        ctx=None,
        tool_provider=SimpleNamespace(
            list_tools=lambda ctx=None: [
                {"name": "web-search"},
                {
                    "name": "memory-search",
                    "semantics": {"concept": "memory", "op": "read", "subject_arg": "query"},
                },
            ]
        ),
    )
    assert advertised_semantics_for(engine, "web-search") is None
    assert advertised_semantics_for(engine, "memory-search") == {
        "concept": "memory",
        "op": "read",
        "subject_arg": "query",
    }
    assert bound_tool_semantics(engine, "memory-search", {"query": "budget"}) == {
        "concept": "memory",
        "op": "read",
        "subject": "budget",
    }
    assert bound_tool_semantics(None, "activate_skill", {"name": "x"}) is None


def test_bind_ignores_non_list_subject_arg():
    advertised = {"concept": "memory", "op": "read", "subject_arg": 1}
    assert bind_tool_semantics(advertised, {"query": "q"}) == {"concept": "memory", "op": "read"}


def test_lookup_missing_provider_or_list_tools():
    assert advertised_semantics_for(SimpleNamespace(tool_provider=None), "x") is None
    assert advertised_semantics_for(SimpleNamespace(tool_provider=object()), "x") is None


def test_lookup_list_tools_without_ctx_kwarg():
    engine = SimpleNamespace(
        tool_provider=SimpleNamespace(list_tools=lambda: [{"name": "t", "semantics": {"concept": "x"}}]),
    )
    assert advertised_semantics_for(engine, "t") == {"concept": "x"}


def test_lookup_list_tools_failures_return_none():
    class _Boom:
        def list_tools(self, *, ctx=None):
            raise RuntimeError("nope")

    class _CtxThenBoom:
        def list_tools(self):
            raise RuntimeError("nope")

    assert advertised_semantics_for(SimpleNamespace(tool_provider=_Boom()), "t") is None
    assert advertised_semantics_for(SimpleNamespace(tool_provider=_CtxThenBoom()), "t") is None


def test_lookup_non_dict_semantics_and_unknown_name():
    engine = SimpleNamespace(
        ctx=None,
        tool_provider=SimpleNamespace(
            list_tools=lambda ctx=None: [
                {"name": "t", "semantics": "not-a-dict"},
                "skip-me",
                {"name": "other"},
            ]
        ),
    )
    assert advertised_semantics_for(engine, "t") is None
    assert advertised_semantics_for(engine, "missing") is None


def test_existing_attr_none():
    assert existing_attr(None, "inner") is None


def test_lookup_rejects_non_sequence_list_tools():
    engine = SimpleNamespace(tool_provider=SimpleNamespace(list_tools=lambda ctx=None: {"name": "t"}))
    assert advertised_semantics_for(engine, "t") is None


def test_lookup_does_not_create_mock_tool_provider():
    from unittest.mock import MagicMock

    engine = MagicMock()
    assert advertised_semantics_for(engine, "activate_skill") is None
    assert "tool_provider" not in engine._mock_children
