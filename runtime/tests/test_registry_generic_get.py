#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mas.runtime.registry import PluginEntry, PluginRegistry, VariantInfo


def test_generic_get_without_name_by_attributes() -> None:
    reg = PluginRegistry()
    reg.register(
        PluginEntry(
            urn="mas.codec.my_codec",
            variants={"builtin": VariantInfo(module="pathlib", class_name="Path")},
            attributes={"artifact_kind": "x", "store_type": "y"},
        )
    )
    info = reg.get("codec", attributes={"artifact_kind": "x", "store_type": "y"})
    assert info is not None
    assert info.class_name == "Path"


def test_generic_get_name_with_attribute_mismatch_returns_none() -> None:
    reg = PluginRegistry()
    reg.register(
        PluginEntry(
            urn="mas.codec.my_codec2",
            shortcuts=["my-codec2"],
            variants={"builtin": VariantInfo(module="pathlib", class_name="Path")},
            attributes={"artifact_kind": "x", "store_type": "y"},
        )
    )
    info = reg.get("codec", "my-codec2", attributes={"artifact_kind": "wrong"})
    assert info is None


def test_generic_get_name_skips_mismatched_candidate_and_returns_next_match() -> None:
    reg = PluginRegistry()
    reg.register(
        PluginEntry(
            urn="mas.codec.first",
            shortcuts=["shared-codec"],
            variants={"builtin": VariantInfo(module="pathlib", class_name="Path")},
            attributes={"artifact_kind": "x", "store_type": "wrong"},
        )
    )
    reg.register(
        PluginEntry(
            urn="mas.codec.second",
            shortcuts=["shared-codec"],
            variants={"builtin": VariantInfo(module="pathlib", class_name="PurePath")},
            attributes={"artifact_kind": "x", "store_type": "right"},
        )
    )

    info = reg.get("codec", "shared-codec", attributes={"artifact_kind": "x", "store_type": "right"})
    assert info is not None
    assert info.class_name == "PurePath"


def test_list_includes_attributes() -> None:
    reg = PluginRegistry()
    reg.register(
        PluginEntry(
            urn="mas.codec.attr_test",
            variants={"builtin": VariantInfo(module="pathlib", class_name="Path")},
            attributes={"artifact_kind": "a", "store_type": "b"},
        )
    )
    items = reg.list()
    target = next(item for item in items if item["urn"] == "mas.codec.attr_test")
    assert target["attributes"]["artifact_kind"] == "a"
    assert target["attributes"]["store_type"] == "b"
    assert target["attributes"]["plugin_type"] == "codec"
