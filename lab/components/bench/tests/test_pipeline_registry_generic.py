#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.lab.benchmark.pipeline import get_step, list_steps, register_step, resolve_step_class


class _DummyStep:
    pass


def test_register_and_get_typed_object() -> None:
    register_step("dummy_step_test", _DummyStep, attributes={"source": "test"})
    assert get_step("dummy_step_test") is _DummyStep


def test_get_with_attribute_filter() -> None:
    register_step("dummy_step_attr", _DummyStep, attributes={"scope": "unit"})
    assert get_step("dummy_step_attr", attributes={"scope": "unit"}) is _DummyStep
    assert get_step("dummy_step_attr", attributes={"scope": "other"}) is None


def test_list_registered_includes_programmatic_entries() -> None:
    register_step("dummy_step_list", _DummyStep, attributes={"source": "programmatic"})
    items = list_steps()
    assert "dummy_step_list" in items
    assert items["dummy_step_list"] is _DummyStep


def test_resolve_class_from_module_path() -> None:
    cls = resolve_step_class("pathlib:Path")
    assert cls.__name__ == "Path"


def test_unknown_step_hints_when_registry_empty(monkeypatch) -> None:
    import pytest
    from mas.lab.benchmark.pipeline import core as pipeline_core

    monkeypatch.setattr(pipeline_core, "get_step", lambda name, **kwargs: None)
    monkeypatch.setattr(pipeline_core, "list_steps", lambda: {})

    def _boom(*_a, **_k):
        raise ImportError("nope")

    monkeypatch.setattr(pipeline_core, "_import_class", _boom)
    with pytest.raises(ValueError, match="No pipeline steps are registered"):
        pipeline_core.resolve_step_class("extract_trace_stats")
