#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.runtime.spec.model_ref import (
    first_nonempty,
    model_binding_by_id,
    resolve_model_ref,
)


def _spec(*models: dict) -> dict:
    return {"spec": {"models": list(models)}}


def test_empty_ref_is_the_agent_engine() -> None:
    assert resolve_model_ref({}, None, engine_model="gpt-4o") == ("gpt-4o", "agent")
    assert resolve_model_ref({}, "  ", engine_model="gpt-4o") == ("gpt-4o", "agent")
    assert resolve_model_ref({}, None, engine_model=None) == (None, "agent")


def test_models_id_resolves_to_provider_string() -> None:
    spec = _spec(
        {"id": "main", "model": "gpt-4o"},
        {"id": "summarizer", "model": "gpt-4o-mini"},
    )
    assert model_binding_by_id(spec, "summarizer")["model"] == "gpt-4o-mini"
    assert resolve_model_ref(spec, "summarizer", engine_model="gpt-4o") == (
        "gpt-4o-mini",
        "spec.models[id=summarizer]",
    )


def test_default_id_is_main() -> None:
    spec = _spec({"model": "gpt-4o"})
    assert model_binding_by_id(spec, "main")["model"] == "gpt-4o"


def test_bare_id_with_no_model_field_falls_back_to_agent() -> None:
    """Do not send a spec.models[].id to the provider as if it were a LiteLLM name."""
    spec = _spec({"id": "summarizer"})
    assert resolve_model_ref(spec, "summarizer", engine_model="gpt-4o") == (
        "gpt-4o",
        "agent",
    )


def test_engine_string_is_agent_not_override() -> None:
    spec = _spec({"id": "main", "model": "gpt-4o"})
    assert resolve_model_ref(spec, "gpt-4o", engine_model="gpt-4o") == (
        "gpt-4o",
        "agent",
    )


def test_unknown_token_is_literal_override() -> None:
    spec = _spec({"id": "main", "model": "gpt-4o"})
    assert resolve_model_ref(spec, "haiku-3", engine_model="gpt-4o") == (
        "haiku-3",
        "override",
    )


def test_accepts_raw_spec_or_full_manifest() -> None:
    raw = {"models": [{"id": "cheap", "model": "gpt-4o-mini"}]}
    assert resolve_model_ref(raw, "cheap", engine_model="gpt-4o")[0] == "gpt-4o-mini"


def test_first_nonempty_skips_blank_and_reports_source() -> None:
    assert first_nonempty(
        ("  ", "a"),
        ("", "b"),
        (None, "c"),
        ("gpt-4o-mini", "experiment.evaluation.model"),
        ("ignored", "later"),
    ) == ("gpt-4o-mini", "experiment.evaluation.model")
    assert first_nonempty(("  ", "a"), (None, "b")) == (None, "")
