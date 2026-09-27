#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Versioned LLM model capability catalog."""

from __future__ import annotations

from mas.runtime.engine.llm_model_catalog import default_model_catalog, load_model_catalog


def test_catalog_loads_curated_models_and_sources():
    catalog = default_model_catalog()
    assert catalog.version
    assert any(s.get("id") == "litellm" for s in catalog.sources)
    gpt5 = catalog.get("openai/gpt-5")
    assert gpt5 is not None
    assert gpt5.context_window == 400000
    assert gpt5.supports("reasoning.effort") is True
    assert gpt5.supports("think") is False
    gemma = catalog.get("gemma-4-26b")
    assert gemma is not None
    assert gemma.supports("think") is True
    assert catalog.get("no-such-model") is None
    assert any(s.get("id") == "models-dev" for s in catalog.sources)
    assert any(s.get("id") == "openclaw" for s in catalog.sources)
    gemini = catalog.get("gemini-2.5-pro")
    assert gemini is not None
    assert gemini.clamp("reasoning.budget_tokens", 99_999) == 32768
    flash = catalog.get("gemini-2.5-flash")
    assert flash is not None
    assert flash.supports("think") is False
    assert flash.supports("reasoning.mode") is False
    assert catalog.get("default") is None
    toy_unlisted = catalog.get("gpt-5-mini")
    assert toy_unlisted is not None
    assert toy_unlisted.supports("include") is False


def test_load_model_catalog_from_path(tmp_path):
    path = tmp_path / "cat.yaml"
    path.write_text(
        """
apiVersion: mas/v1
kind: LlmModelCatalog
metadata: {name: t, version: "1"}
spec:
  sources: []
  models:
    toy:
      context_window: 8
      settings:
        think: {supported: false}
""",
        encoding="utf-8",
    )
    catalog = load_model_catalog(path)
    assert catalog.get("toy").context_window == 8
    assert catalog.get("toy").supports("think") is False
