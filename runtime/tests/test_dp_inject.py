#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for inject_dp_protocol after the switch to the generic
registry.get("design_pattern", ...) lookup."""

from __future__ import annotations

import mas.runtime.boundary.context.dp_inject as dp_inject
from mas.runtime.boundary.context.dp_inject import inject_dp_protocol


class _Info:
    def __init__(self, cls: type) -> None:
        self._cls = cls

    def load_class(self) -> type:
        return self._cls


class _FakeRegistry:
    def __init__(self, cls: type | None) -> None:
        self._cls = cls

    def get(self, plugin_type: str, name: str):  # noqa: ANN001
        assert plugin_type == "design_pattern"
        return _Info(self._cls) if self._cls is not None else None


def _patch(monkeypatch, cls: type | None) -> None:
    monkeypatch.setattr(dp_inject, "get_registry", lambda: _FakeRegistry(cls))


def test_unknown_pattern_returns_injected_unchanged(monkeypatch) -> None:
    _patch(monkeypatch, None)
    assert inject_dp_protocol(["a"], pattern_plugin_id="nope") == ["a"]


def test_plugin_without_protocol_lines_returns_injected(monkeypatch) -> None:
    class NoProto:
        pass

    _patch(monkeypatch, NoProto)
    assert inject_dp_protocol(["a"], pattern_plugin_id="x") == ["a"]


def test_plugin_with_empty_protocol_lines_returns_injected(monkeypatch) -> None:
    class EmptyProto:
        def protocol_lines(self, q):  # noqa: ANN001
            return []

    _patch(monkeypatch, EmptyProto)
    assert inject_dp_protocol(["a"], pattern_plugin_id="x") == ["a"]


def test_plugin_with_protocol_lines_extends(monkeypatch) -> None:
    class WithProto:
        def protocol_lines(self, q):  # noqa: ANN001
            return ["p1", "p2"]

    _patch(monkeypatch, WithProto)
    out = inject_dp_protocol(["a"], pattern_plugin_id="x")
    assert out == ["a", "p1", "p2"]
    # Original list is not mutated.
    assert inject_dp_protocol(["a"], pattern_plugin_id="x") == ["a", "p1", "p2"]
