#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.runtime.registry import PluginRegistry
from mas.runtime.registry.bootstrap import register_manifest_data


def test_eval_metric_type_from_manifest_types_list() -> None:
    registry = PluginRegistry()
    register_manifest_data(
        registry,
        {
            "types": ["eval_metric"],
            "plugins": [
                {
                    "type": "eval_metric",
                    "name": "toy_echo",
                    "module": "mas.library.eval.metrics.toy",
                    "class": "ToyEchoMetric",
                    "attributes": {"provider": "mce"},
                }
            ],
        },
    )
    assert registry.resolve_by_type("eval_metric", "toy_echo") is not None
    names = registry.list_names("eval_metric")
    assert "toy_echo" in names


def test_eval_metric_factory_only_registers() -> None:
    registry = PluginRegistry()
    register_manifest_data(
        registry,
        {
            "types": ["eval_metric"],
            "plugins": [
                {
                    "type": "eval_metric",
                    "name": "family",
                    "factory": "mas.library.eval.metrics.toy:ToyEchoMetric",
                    "provider": "mce",
                    "description": "factory-shaped family declaration",
                }
            ],
        },
    )
    entry = registry.get_entry("mas.eval_metric.family")
    assert entry is not None
    assert entry.attributes.get("factory")
    assert entry.attributes.get("provider") == "mce"
