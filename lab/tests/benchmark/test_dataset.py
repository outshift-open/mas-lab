#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for benchmark dataset module."""

import tempfile
import yaml
from pathlib import Path

from mas.lab.benchmark import Dataset, DatasetItem
from mas.lab.inputs import RunInput


def test_dataset_item_from_dict():
    """Test DatasetItem creation from envelope dictionary."""
    data = {
        "id": "001",
        "inputs": {
            "user": [{"role": "user", "content": "What is 2+2?"}],
        },
        "expectations": {"ground_truth": "4"},
        "category": "math",
        "difficulty": "easy",
    }

    item = DatasetItem.from_dict(data)

    assert item.id == "001"
    assert item.prompt == "What is 2+2?"
    assert item.run_input.expectations["ground_truth"] == "4"
    assert item.metadata["category"] == "math"
    assert item.metadata["difficulty"] == "easy"


def test_dataset_from_yaml():
    """Test Dataset loading from manifest format (lab/v1)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        manifest = {
            "apiVersion": "lab/v1",
            "kind": "Dataset",
            "metadata": {
                "name": "manifest-dataset",
                "version": "2.0",
                "description": "Manifest-wrapped dataset",
                "tags": ["test"],
            },
            "spec": {
                "items": [
                    {
                        "id": "m1",
                        "inputs": {"user": [{"role": "user", "content": "MQ1"}]},
                        "category": "travel",
                    },
                    {
                        "id": "m2",
                        "inputs": {"user": [{"role": "user", "content": "MQ2"}]},
                        "category": "travel",
                    },
                    {
                        "id": "m3",
                        "inputs": {"user": [{"role": "user", "content": "MQ3"}]},
                        "category": "tech",
                    },
                ]
            },
        }
        yaml.dump(manifest, f)
        temp_path = Path(f.name)

    try:
        dataset = Dataset.from_yaml(temp_path)
        assert dataset.name == "manifest-dataset"
        assert dataset.version == "2.0"
        assert len(dataset) == 3
        assert dataset[0].id == "m1"
        assert dataset[2].metadata["category"] == "tech"
    finally:
        temp_path.unlink()


def test_dataset_filter():
    """Test dataset filtering on metadata fields."""
    items = [
        DatasetItem(
            id="001",
            run_input=RunInput(user=[{"role": "user", "content": "Q1"}]),
            metadata={"category": "math"},
        ),
        DatasetItem(
            id="002",
            run_input=RunInput(user=[{"role": "user", "content": "Q2"}]),
            metadata={"category": "logic"},
        ),
        DatasetItem(
            id="003",
            run_input=RunInput(user=[{"role": "user", "content": "Q3"}]),
            metadata={"category": "math"},
        ),
    ]

    dataset = Dataset(name="test", items=items)
    filtered = dataset.filter(category="math")

    assert len(filtered) == 2
    assert filtered[0].id == "001"
    assert filtered[1].id == "003"


def test_dataset_iteration():
    """Test dataset iteration."""
    items = [
        DatasetItem(
            id="001",
            run_input=RunInput(user=[{"role": "user", "content": "Q1"}]),
        ),
        DatasetItem(
            id="002",
            run_input=RunInput(user=[{"role": "user", "content": "Q2"}]),
        ),
    ]

    dataset = Dataset(name="test", items=items)

    item_ids = [item.id for item in dataset]
    assert item_ids == ["001", "002"]
