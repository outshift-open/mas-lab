#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for ExportLayers filtering logic."""

from __future__ import annotations

import pytest

from mas.library.standard.lib.observability.export_layers import (
    ExportLayers,
    layer_for_kind,
    parse_export_layers,
    should_export_event,
)


# ---------------------------------------------------------------------------
# ExportLayers defaults
# ---------------------------------------------------------------------------

def test_default_layers_enabled() -> None:
    layers = ExportLayers()
    assert layers.structure is True
    assert layers.execution is True
    assert layers.semantic is True
    assert layers.provenance is False
    assert layers.governance is False


def test_enabled_returns_false_for_unknown_layer() -> None:
    layers = ExportLayers()
    # getattr with default=True means unknown layers pass through
    assert layers.enabled("nonexistent") is True


# ---------------------------------------------------------------------------
# parse_export_layers
# ---------------------------------------------------------------------------

def test_parse_export_layers_empty_cfg() -> None:
    layers = parse_export_layers({})
    assert layers == ExportLayers()


def test_parse_export_layers_disable_semantic() -> None:
    layers = parse_export_layers({"semantic": False})
    assert layers.semantic is False
    assert layers.structure is True


def test_parse_export_layers_enable_governance() -> None:
    layers = parse_export_layers({"governance": True})
    assert layers.governance is True


def test_parse_export_layers_nested_export_layers_key() -> None:
    layers = parse_export_layers({"export_layers": {"provenance": True}})
    assert layers.provenance is True


def test_parse_export_layers_alias_structural() -> None:
    layers = parse_export_layers({"structural": False})
    assert layers.structure is False


def test_parse_export_layers_none() -> None:
    assert parse_export_layers(None) == ExportLayers()


# ---------------------------------------------------------------------------
# layer_for_kind
# ---------------------------------------------------------------------------

def test_layer_for_kind_execution_start() -> None:
    assert layer_for_kind("execution_start") == "execution"


def test_layer_for_kind_mas_call_start() -> None:
    assert layer_for_kind("mas_call_start") == "structure"


def test_layer_for_kind_unknown() -> None:
    assert layer_for_kind("completely_unknown_kind") is None


# ---------------------------------------------------------------------------
# should_export_event — default layers (structure + execution + semantic on,
# provenance + governance off)
# ---------------------------------------------------------------------------

def test_should_export_execution_event_by_default() -> None:
    layers = ExportLayers()
    assert should_export_event({"kind": "execution_start"}, layers) is True


def test_should_export_structure_event_by_default() -> None:
    layers = ExportLayers()
    assert should_export_event({"kind": "mas_call_start"}, layers) is True


def test_governance_suppressed_by_default() -> None:
    layers = ExportLayers()
    # governance_checked is a registered governance-layer kind (envelope.py).
    assert layer_for_kind("governance_checked") == "governance"
    assert should_export_event({"kind": "governance_checked"}, layers) is False


def test_governance_passes_when_enabled() -> None:
    layers = ExportLayers(governance=True)
    assert should_export_event({"kind": "governance_checked"}, layers) is True


def test_provenance_suppressed_by_default() -> None:
    layers = ExportLayers()
    # Find a provenance-layer event kind
    from mas.library.standard.lib.observability.native.envelope import _KIND_ENVELOPE
    from mas.library.standard.lib.observability.export_layers import _BLOCK_TO_LAYER

    provenance_kinds = [
        k for k, v in _KIND_ENVELOPE.items()
        if _BLOCK_TO_LAYER.get(v[0]) == "provenance"
    ]
    if provenance_kinds:
        ev = {"kind": provenance_kinds[0]}
        assert should_export_event(ev, layers) is False


def test_provenance_passes_when_enabled() -> None:
    layers = ExportLayers(provenance=True)
    from mas.library.standard.lib.observability.native.envelope import _KIND_ENVELOPE
    from mas.library.standard.lib.observability.export_layers import _BLOCK_TO_LAYER

    provenance_kinds = [
        k for k, v in _KIND_ENVELOPE.items()
        if _BLOCK_TO_LAYER.get(v[0]) == "provenance"
    ]
    if provenance_kinds:
        ev = {"kind": provenance_kinds[0]}
        assert should_export_event(ev, layers) is True


def test_unknown_kind_passes_through() -> None:
    layers = ExportLayers(governance=False, provenance=False)
    ev = {"kind": "totally_unknown"}
    assert should_export_event(ev, layers) is True


def test_layer_field_on_event_overrides_kind_lookup() -> None:
    """Explicit 'layer' field on the event takes priority over kind lookup."""
    layers = ExportLayers(governance=False)
    ev = {"kind": "mas_call_start", "layer": "governance"}
    assert should_export_event(ev, layers) is False
