#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas.library.kg.observability.extractors — pure functions."""

from __future__ import annotations

from mas.library.kg.observability.extractors import (
    extract_model,
    extract_tokens,
    ioa_span_kind,
    is_llm_span,
    normalize_attrs,
    otel_ts_to_epoch,
    stable_id,
)


class TestNormalizeAttrs:
    def test_dict_input_returned_as_is(self):
        attrs = {"key": "val"}
        assert normalize_attrs(attrs) == {"key": "val"}

    def test_none_returns_empty_dict(self):
        assert normalize_attrs(None) == {}

    def test_json_string_input_parsed(self):
        import json

        attrs_json = json.dumps({"a": "b"})
        result = normalize_attrs(attrs_json)
        assert result == {"a": "b"}

    def test_invalid_json_string_returns_empty(self):
        result = normalize_attrs("not json {{{")
        assert result == {}

    def test_nested_values_preserved(self):
        attrs = {"nested": {"x": 1}, "list": [1, 2, 3]}
        assert normalize_attrs(attrs) == attrs


class TestStableId:
    def test_same_inputs_produce_same_id(self):
        assert stable_id("run-1", "span-abc") == stable_id("run-1", "span-abc")

    def test_different_run_id_produces_different_id(self):
        assert stable_id("run-1", "span-abc") != stable_id("run-2", "span-abc")

    def test_different_span_id_produces_different_id(self):
        assert stable_id("run-1", "span-abc") != stable_id("run-1", "span-xyz")

    def test_result_is_string(self):
        result = stable_id("run-1", "span-1")
        assert isinstance(result, str)
        assert len(result) == 32


class TestOtelTsToEpoch:
    def test_nanoseconds_integer_converted(self):
        # 1704067200000000000 ns = 1704067200.0 s
        result = otel_ts_to_epoch(1_704_067_200_000_000_000)
        assert abs(result - 1_704_067_200.0) < 1.0

    def test_nanoseconds_string_converted(self):
        result = otel_ts_to_epoch("1704067200000000000")
        assert abs(result - 1_704_067_200.0) < 1.0

    def test_iso8601_string_converted(self):
        result = otel_ts_to_epoch("2024-01-01T00:00:00Z")
        assert abs(result - 1_704_067_200.0) < 2.0

    def test_float_seconds_passthrough(self):
        # Small float — already seconds, not nanoseconds
        result = otel_ts_to_epoch(1_704_067_200.0)
        assert abs(result - 1_704_067_200.0) < 1.0

    def test_none_returns_zero(self):
        assert otel_ts_to_epoch(None) == 0.0


class TestIoaSpanKind:
    def test_span_kind_from_ioa_observe_attr(self):
        from mas.library.kg.observability.vocabulary import IoaObserveAttrs

        attrs = {IoaObserveAttrs.SPAN_KIND: "agent"}
        assert ioa_span_kind(attrs) == "agent"

    def test_span_kind_from_legacy_traceloop_attr(self):
        from mas.library.kg.observability.vocabulary import IoaObserveAttrs

        attrs = {IoaObserveAttrs.SPAN_KIND_LEGACY: "tool"}
        assert ioa_span_kind(attrs) == "tool"

    def test_ioa_observe_attr_takes_precedence_over_legacy(self):
        from mas.library.kg.observability.vocabulary import IoaObserveAttrs

        attrs = {
            IoaObserveAttrs.SPAN_KIND: "agent",
            IoaObserveAttrs.SPAN_KIND_LEGACY: "tool",
        }
        assert ioa_span_kind(attrs) == "agent"

    def test_missing_returns_none(self):
        assert ioa_span_kind({}) is None


class TestIsLlmSpan:
    def test_span_with_gen_ai_operation_is_llm(self):
        from mas.library.kg.observability.vocabulary import GenAIAttrs

        attrs = {GenAIAttrs.OPERATION: "chat"}
        assert is_llm_span(attrs) is True

    def test_span_without_gen_ai_operation_is_not_llm(self):
        attrs = {"other.attr": "value"}
        assert is_llm_span(attrs) is False

    def test_empty_attrs_is_not_llm(self):
        assert is_llm_span({}) is False


class TestExtractModel:
    def test_response_model_preferred(self):
        from mas.library.kg.observability.vocabulary import GenAIAttrs

        attrs = {
            GenAIAttrs.RESP_MODEL: "gpt-4-turbo",
            GenAIAttrs.REQ_MODEL: "gpt-4",
        }
        assert extract_model(attrs) == "gpt-4-turbo"

    def test_request_model_fallback(self):
        from mas.library.kg.observability.vocabulary import GenAIAttrs

        attrs = {GenAIAttrs.REQ_MODEL: "gpt-4"}
        assert extract_model(attrs) == "gpt-4"

    def test_no_model_returns_none(self):
        assert extract_model({}) is None


class TestExtractTokens:
    def test_extracts_all_token_fields(self):
        from mas.library.kg.observability.vocabulary import GenAIAttrs

        attrs = {
            GenAIAttrs.IN_TOKENS: 100,
            GenAIAttrs.OUT_TOKENS: 50,
            GenAIAttrs.TOTAL_TOKENS: 150,
        }
        result = extract_tokens(attrs)
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["total_tokens"] == 150

    def test_missing_tokens_returns_none_values(self):
        result = extract_tokens({})
        assert result.get("prompt_tokens") is None
        assert result.get("completion_tokens") is None

    def test_string_token_values_coerced_to_int(self):
        from mas.library.kg.observability.vocabulary import GenAIAttrs

        attrs = {GenAIAttrs.IN_TOKENS: "42"}
        result = extract_tokens(attrs)
        assert result["prompt_tokens"] == 42
