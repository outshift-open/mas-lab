#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""History budget = model context window minus completion reserve."""

from __future__ import annotations

from mas.runtime.boundary.context.assembly_trim import (
    assembly_trimmer_params,
    context_manager_history_budget_hint,
)
from mas.runtime.spec.history_budget import (
    derived_trimmer_params,
    fill_context_manager_defaults,
    history_token_budget,
    model_completion_tokens,
    model_context_window,
)


def test_defaults_when_models_omitted() -> None:
    spec = {"description": "bare"}
    assert model_context_window({"spec": spec}) == 128000
    assert model_completion_tokens({"spec": spec}) == 2000
    assert derived_trimmer_params({"spec": spec}) == (128000, 2000)
    assert history_token_budget({"spec": spec}) == 126000


def test_explicit_model_window_and_completion() -> None:
    manifest = {
        "spec": {
            "models": [{"model": "haiku", "context_window": 200000, "max_tokens": 4096}],
        }
    }
    assert derived_trimmer_params(manifest) == (200000, 4096)
    assert history_token_budget(manifest) == 200000 - 4096


def test_explicit_trimmer_wins() -> None:
    manifest = {
        "spec": {
            "models": [{"model": "gpt-4o", "context_window": 128000, "max_tokens": 2000}],
            "context_manager": {
                "type": "summarising",
                "params": {"trimmer": {"max_tokens": 12000, "reserve_tokens": 512}},
            },
        }
    }
    assert assembly_trimmer_params(manifest) == (12000, 512)
    assert context_manager_history_budget_hint(manifest) == 12000 - 512


def test_fill_context_manager_defaults_emits_sota_summarising() -> None:
    spec = {"models": [{"model": "gpt-4o", "max_tokens": 1800}]}
    fill_context_manager_defaults(spec)
    cm = spec["context_manager"]
    assert cm["type"] == "summarising"
    assert cm["params"]["keep_turns"] == 10
    assert cm["params"]["hysteresis_ratio"] == 0.2
    assert spec["models"][0]["context_window"] == 128000
    assert cm["params"]["trimmer"] == {"max_tokens": 128000, "reserve_tokens": 1800}
    assert cm["params"]["summary_threshold"] == 128000 - 1800


def test_fill_preserves_explicit_keep_turns_and_sliding_window() -> None:
    spec = {
        "models": [{"model": "gpt-4o", "context_window": 8000, "max_tokens": 500}],
        "context_manager": {"type": "sliding-window", "params": {"keep_turns": 3}},
    }
    fill_context_manager_defaults(spec)
    params = spec["context_manager"]["params"]
    assert params["keep_turns"] == 3
    assert params["window_size"] == 3
    assert "summary_threshold" not in params
    assert params["trimmer"]["max_tokens"] == 8000
    assert params["trimmer"]["reserve_tokens"] == 500
