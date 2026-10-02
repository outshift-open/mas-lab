#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
from mas.runtime.harness.catalog import (
    CyclicHarnessError,
    HarnessCatalog,
    HarnessComposition,
    IllegalHarnessLeafError,
    UnknownBoundarySlotError,
    assert_boundary_slot,
    default_catalog,
)
from mas.runtime.registry import PluginRegistry


def test_builtin_harness_dag_closes_on_kernel_ops() -> None:
    catalog = default_catalog()
    assert "evolution" in catalog
    assert "detective" in catalog.depends("evolution")
    leaves = catalog.uses_closed("evolution")
    assert "snapshot" in leaves
    assert "spec_delta" in leaves
    assert "pause" in leaves
    assert "httpx" not in leaves


def test_illegal_leaf_is_a_fourth_path() -> None:
    catalog = default_catalog()
    with pytest.raises(IllegalHarnessLeafError, match="fourth path"):
        catalog.register(
            HarnessComposition(name="sneaky", uses=("httpx",), description="nope")
        )


def test_cycle_is_rejected() -> None:
    catalog = HarnessCatalog()
    catalog.register(HarnessComposition(name="a", uses=("step",), requires=("b",)))
    with pytest.raises((CyclicHarnessError, IllegalHarnessLeafError, KeyError)):
        catalog.register(HarnessComposition(name="b", uses=("step",), requires=("a",)))
        catalog.depends("a")


def test_new_boundary_slot_is_rejected() -> None:
    with pytest.raises(UnknownBoundarySlotError, match="15th hook|closed"):
        assert_boundary_slot("pre_tool_use")
    registry = PluginRegistry()
    with pytest.raises(UnknownBoundarySlotError):
        registry.register_type("pre_tool_use", layer="boundary")
    registry.register_type("step")
