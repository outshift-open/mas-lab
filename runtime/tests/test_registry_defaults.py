#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for runtime default-plugin loading and overrides."""

from __future__ import annotations

from mas.runtime.agent_defaults import (
    agent_defaults,
    default_context_manager_id,
    default_model,
    default_pattern_plugin_id,
    resolve_default_model,
)
from mas.runtime.registry.bootstrap import load_registry
from mas.runtime.registry.defaults import (
    load_config_defaults,
    load_default_defaults,
    load_defaults,
    validate_defaults_manifest,
)
from mas.runtime.workspace_config import RuntimeWorkspaceConfig


def test_default_defaults_loaded_from_package_data() -> None:
    defaults = load_default_defaults()

    assert defaults["model"] == "gpt-4o-mini"
    assert defaults["design_pattern"] == "react@v1"
    assert defaults["context_manager"] == "sliding-window"


def test_workspace_defaults_override_package_defaults(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text(
        """defaults:
  model: gpt-4.1-mini
  design_pattern: cot@v1
""",
        encoding="utf-8",
    )

    config = RuntimeWorkspaceConfig.load(start=workspace)
    merged = load_defaults(config)

    # Overridden keys win...
    assert merged["model"] == "gpt-4.1-mini"
    assert merged["design_pattern"] == "cot@v1"
    # ...untouched keys fall back to the package default.
    assert merged["context_manager"] == "sliding-window"


def test_registry_set_default_reflects_workspace_override(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text(
        """defaults:
  design_pattern: cot@v1
""",
        encoding="utf-8",
    )

    config = RuntimeWorkspaceConfig.load(start=workspace)
    registry = load_registry(config)

    assert registry.default_for("design_pattern") == "cot@v1"
    # context_manager wasn't overridden, so the package default still applies.
    assert registry.default_for("context_manager") == "sliding-window"


def test_registry_does_not_register_model_as_a_spec_default() -> None:
    registry = load_registry()

    # "model" is a plain string default (see agent_defaults.default_model()),
    # not a registry plugin type/spec_key -- PluginRegistry.default_for()
    # returns "" for any spec_key that was never set_default()'d.
    assert registry.default_for("model") == ""


def test_agent_defaults_accessors_use_single_source_of_truth() -> None:
    assert default_pattern_plugin_id() == "react@v1"
    assert default_context_manager_id() == "sliding-window"
    assert default_model() == "gpt-4o-mini"
    assert resolve_default_model() == "gpt-4o-mini"

    defaults = agent_defaults()
    assert defaults["design_pattern"]["type"] == "react@v1"
    assert defaults["models"][0]["model"] == "gpt-4o-mini"


def test_resolve_default_model_prefers_explicit_workspace_object() -> None:
    class _Workspace:
        default_model = "gpt-explicit"

    assert resolve_default_model(_Workspace()) == "gpt-explicit"

    class _CallableWorkspace:
        @staticmethod
        def default_model() -> str:
            return "gpt-callable"

    assert resolve_default_model(_CallableWorkspace()) == "gpt-callable"


def test_load_config_defaults_empty_when_no_workspace(tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    config = RuntimeWorkspaceConfig.load(start=empty)

    assert load_config_defaults(config) == {}


def test_validate_defaults_manifest_rejects_invalid_value() -> None:
    try:
        validate_defaults_manifest({"model": 123}, name="bad")
    except ValueError as exc:
        assert "invalid defaults manifest" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_validate_defaults_manifest_rejects_unknown_key() -> None:
    try:
        validate_defaults_manifest({"unknown_key": "x"}, name="bad")
    except ValueError as exc:
        assert "invalid defaults manifest" in str(exc)
    else:
        raise AssertionError("expected validation error")
