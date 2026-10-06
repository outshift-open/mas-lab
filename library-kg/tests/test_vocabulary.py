#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas.library.kg.observability.vocabulary — attribute key constants."""

from __future__ import annotations

from mas.library.kg.observability.vocabulary import (
    SUPPRESSED_IOA_OBSERVE_NAMES,
    GenAIAttrs,
    IoaObserveAttrs,
    MasBoundaryAttrs,
)


class TestIoaObserveAttrs:
    def test_span_kind_is_string(self):
        assert isinstance(IoaObserveAttrs.SPAN_KIND, str)

    def test_span_kind_legacy_differs_from_span_kind(self):
        assert IoaObserveAttrs.SPAN_KIND != IoaObserveAttrs.SPAN_KIND_LEGACY

    def test_all_attrs_are_nonempty_strings(self):
        for name in vars(IoaObserveAttrs):
            if name.startswith("_"):
                continue
            val = getattr(IoaObserveAttrs, name)
            assert isinstance(val, str) and val, f"IoaObserveAttrs.{name} is empty"


class TestGenAIAttrs:
    def test_all_attrs_are_nonempty_strings(self):
        for name in vars(GenAIAttrs):
            if name.startswith("_"):
                continue
            val = getattr(GenAIAttrs, name)
            assert isinstance(val, str) and val, f"GenAIAttrs.{name} is empty"

    def test_token_fields_are_distinct(self):
        assert len({GenAIAttrs.IN_TOKENS, GenAIAttrs.OUT_TOKENS, GenAIAttrs.TOTAL_TOKENS}) == 3


class TestMasBoundaryAttrs:
    def test_all_attrs_are_nonempty_strings(self):
        for name in vars(MasBoundaryAttrs):
            if name.startswith("_"):
                continue
            val = getattr(MasBoundaryAttrs, name)
            assert isinstance(val, str) and val

    def test_boundary_key_starts_with_mas(self):
        assert MasBoundaryAttrs.BOUNDARY.startswith("mas.")


class TestSuppressedNames:
    def test_is_frozenset(self):
        assert isinstance(SUPPRESSED_IOA_OBSERVE_NAMES, frozenset)

    def test_contains_agent_start_end_events(self):
        assert "agent_start_event" in SUPPRESSED_IOA_OBSERVE_NAMES
        assert "agent_end_event" in SUPPRESSED_IOA_OBSERVE_NAMES

    def test_all_elements_are_strings(self):
        for name in SUPPRESSED_IOA_OBSERVE_NAMES:
            assert isinstance(name, str)
