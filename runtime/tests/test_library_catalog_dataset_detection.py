#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Datasets are recognised by content, never by directory name."""

from __future__ import annotations

from pathlib import Path

from mas.library_catalog import _looks_like_dataset


def test_fixture_payload_with_metadata_is_not_a_dataset(tmp_path: Path):
    path = tmp_path / "payload.yaml"
    path.write_text("metadata: {name: x}\nservices: {}\n", encoding="utf-8")
    assert not _looks_like_dataset(path)


def test_typed_and_untyped_item_lists_are_datasets(tmp_path: Path):
    typed = tmp_path / "a.yaml"
    typed.write_text("kind: Dataset\nspec: {items: []}\n", encoding="utf-8")
    untyped = tmp_path / "b.yaml"
    untyped.write_text("items: []\n", encoding="utf-8")
    assert _looks_like_dataset(typed)
    assert _looks_like_dataset(untyped)
