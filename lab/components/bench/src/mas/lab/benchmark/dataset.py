#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""
Dataset management for benchmarks — envelope-only items (inputs / expectations).
"""


from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from mas.lab.inputs import RunInput, load_run_input, run_input_to_dict


@dataclass
class DatasetItem:
    id: str
    run_input: RunInput
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def prompt(self) -> str:
        return self.run_input.primary_prompt

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        base_path: Optional[Path] = None,
        *,
        scenario: Optional[Dict[str, Any]] = None,
        experiment: Optional[Dict[str, Any]] = None,
    ) -> DatasetItem:
        run = load_run_input(
            data,
            scenario=scenario,
            experiment=experiment,
            base_path=base_path,
        )
        reserved = {"id", "inputs", "expectations"}
        return cls(
            id=str(data["id"]),
            run_input=run,
            metadata={k: v for k, v in data.items() if k not in reserved},
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {"id": self.id, **run_input_to_dict(self.run_input)}
        result.update(self.metadata)
        return result


class Dataset:
    def __init__(
        self,
        name: str,
        items: List[DatasetItem],
        version: str = "v1",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.items = items
        self.metadata = metadata or {}

    @classmethod
    def from_yaml(cls, path: Path) -> Dataset:
        from mas.runtime.spec.source import load_yaml_file

        data = load_yaml_file(path)

        raw_items = (
            data.get("spec", {}).get("items")
            or data.get("items")
            or []
        )
        base_path = Path(path).parent
        items = [DatasetItem.from_dict(item, base_path=base_path) for item in raw_items]

        meta = data.get("metadata") or {}
        spec = data.get("spec") or {}
        return cls(
            name=meta.get("name") or data.get("name") or data.get("dataset") or path.stem,
            version=meta.get("version") or data.get("version", "v1"),
            description=meta.get("description") or data.get("description", ""),
            items=items,
            metadata={
                k: v
                for k, v in data.items()
                if k
                not in [
                    "apiVersion",
                    "kind",
                    "metadata",
                    "spec",
                    "name",
                    "dataset",
                    "version",
                    "description",
                    "items",
                ]
            },
        )

    def to_yaml(self, path: Path) -> None:
        import yaml

        data = {
            "apiVersion": "lab/v1",
            "kind": "Dataset",
            "metadata": {
                "name": self.name,
                "version": self.version,
                "description": self.description,
            },
            "spec": {"items": [item.to_dict() for item in self.items]},
            **self.metadata,
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                width=120,
            )

    def filter(self, **kwargs) -> Dataset:
        filtered_items = []
        for item in self.items:
            match = True
            for key, value in kwargs.items():
                if key == "category":
                    if item.metadata.get("category") != value:
                        match = False
                        break
                elif item.metadata.get(key) != value and getattr(item.run_input, key, None) != value:
                    if item.metadata.get(key) != value:
                        match = False
                        break
            if match:
                filtered_items.append(item)

        return Dataset(
            name=f"{self.name}_filtered",
            items=filtered_items,
            version=self.version,
            description=f"Filtered: {self.description}",
            metadata=self.metadata,
        )

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[DatasetItem]:
        return iter(self.items)

    def __getitem__(self, idx: int) -> DatasetItem:
        return self.items[idx]
