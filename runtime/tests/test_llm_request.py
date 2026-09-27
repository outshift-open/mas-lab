#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Static sampling / extra_body from spec.models[]."""

from __future__ import annotations

from mas.runtime.engine.llm_request import (
    apply_sampling_payload,
    extra_from_manifest,
    sampling_settings_from_manifest,
)


def test_sampling_from_spec_models_not_llm():
    settings = sampling_settings_from_manifest(
        {
            "spec": {
                "models": [{"model": "m", "top_p": 0.2, "seed": 7}],
                "llm": {"top_p": 0.9, "temperature": 0.1},
            }
        }
    )
    assert settings.get("top_p") == 0.2
    assert settings.get("seed") == 7
    assert settings.get("temperature") == 0.1


def test_apply_sampling_skips_max_tokens():
    from mas.runtime.engine.llm_request import SamplingSettings

    payload = apply_sampling_payload(
        {"max_tokens": 10, "model": "m"},
        SamplingSettings({"max_tokens": 99, "top_k": 4}),
    )
    assert payload["max_tokens"] == 10
    assert payload["top_k"] == 4


def test_extra_from_models_wins_over_llm():
    extra = extra_from_manifest(
        {
            "spec": {
                "llm": {"extra": {"a": 1, "b": 2}},
                "models": [{"model": "m", "extra": {"b": 3, "c": 4}}],
            }
        }
    )
    assert extra == {"a": 1, "b": 3, "c": 4}


def test_model_entry_matches_id_or_name():
    from mas.runtime.engine.llm_request import model_entry_from_manifest

    manifest = {
        "spec": {
            "models": [
                {"id": "main", "model": "gpt-4o", "temperature": 0.1},
                {"id": "alt", "model": "gpt-5-mini", "temperature": 0.9, "extra": {"x": 1}},
            ]
        }
    }
    row = model_entry_from_manifest(manifest, model="gpt-5-mini")
    assert row is not None
    assert row["id"] == "alt"
    assert extra_from_manifest(manifest, model="alt") == {"x": 1}
    settings = sampling_settings_from_manifest(manifest, model="gpt-5-mini")
    assert settings.get("temperature") == 0.9


def test_sampling_includes_min_p_and_max_completion_tokens():
    settings = sampling_settings_from_manifest(
        {"spec": {"models": [{"model": "m", "min_p": 0.05, "max_completion_tokens": 128, "repetition_penalty": 1.1}]}}
    )
    assert settings.get("min_p") == 0.05
    assert settings.get("max_completion_tokens") == 128
    assert settings.get("repetition_penalty") == 1.1
