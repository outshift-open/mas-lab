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


# ``spec.path`` sidecar suffix/format_hint -> the same ``spec.source.kind``
# strings used by :mod:`mas.lab.benchmark.dataset_source`, so both dispatch
# through its one ``SOURCE_LOADERS`` table instead of two independent chains.
_SPEC_PATH_KIND_BY_SUFFIX = {".jsonl": "jsonl", ".csv": "csv"}


def _load_spec_path(
    path_text: Any,
    *,
    base_path: Path,
    format_hint: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load ``spec.path`` sidecar items (YAML / JSONL / CSV)."""
    if not path_text:
        return []
    target = Path(str(path_text))
    if not target.is_absolute():
        target = base_path / target
    suffix = target.suffix.lower()
    hint = str(format_hint or "").lower()
    if suffix == ".json" or hint == "json":
        raise ValueError(
            f"Dataset spec.path no longer accepts JSON ({target}); "
            "inline spec.items in YAML or use spec.source (jsonl/csv/huggingface)"
        )
    if not target.is_file():
        return []
    kind = _SPEC_PATH_KIND_BY_SUFFIX.get(suffix) or (
        hint if hint in _SPEC_PATH_KIND_BY_SUFFIX.values() else None
    )
    if kind is not None:
        from mas.lab.benchmark.dataset_source import SOURCE_LOADERS

        return SOURCE_LOADERS[kind]({"path": str(target)}, base_path)
    from mas.runtime.spec.source import load_yaml_file

    data = load_yaml_file(target)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("items") or (data.get("spec") or {}).get("items") or []
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


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
        source: Optional[Path] = None,
    ) -> DatasetItem:
        run = load_run_input(
            data,
            scenario=scenario,
            experiment=experiment,
            base_path=base_path,
            source=source,
        )
        reserved = {"id", "inputs", "expectations"}
        item_id = data.get("id")
        if item_id is None or item_id == "":
            item_id = "item"
        return cls(
            id=str(item_id),
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
        app: Optional[Any] = None,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.items = items
        self.metadata = metadata or {}
        self.app = app

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        *,
        source_overlay: Optional[Dict[str, Any]] = None,
    ) -> Dataset:
        from mas.runtime.spec.source import load_yaml_file

        data = load_yaml_file(path)
        if isinstance(data, list):
            from mas.lab.deprecations import warn_deprecated

            warn_deprecated("dataset.bare_list", where=str(path))
            data = {"spec": {"items": [item for item in data if isinstance(item, dict)]}}
        if not isinstance(data, dict):
            data = {}

        spec = data.get("spec") or {}
        raw_items = spec.get("items") or data.get("items") or []
        base_path = Path(path).parent
        source = spec.get("source")
        if source_overlay:
            source = {**(source or {}), **source_overlay}
        if source:
            from mas.lab.benchmark.dataset_source import materialize_source

            sourced = materialize_source(source, base_path=base_path)
            if raw_items:
                sourced.extend(raw_items)
            raw_items = sourced
        elif spec.get("path") and not raw_items:
            raw_items = _load_spec_path(
                spec["path"],
                base_path=base_path,
                format_hint=spec.get("format"),
            )
        items = [
            DatasetItem.from_dict(item, base_path=base_path, source=path)
            for item in raw_items
            if isinstance(item, dict)
        ]

        meta = data.get("metadata") or {}
        return cls(
            name=meta.get("name") or data.get("name") or data.get("dataset") or path.stem,
            version=meta.get("version") or data.get("version", "v1"),
            description=meta.get("description") or data.get("description", ""),
            items=items,
            app=spec.get("app") or meta.get("app") or data.get("app"),
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
                    "app",
                ]
            },
        )

    def to_yaml(self, path: Path) -> None:
        import yaml

        spec: Dict[str, Any] = {"items": [item.to_dict() for item in self.items]}
        if self.app:
            spec = {"app": self.app, **spec}
        data = {
            "apiVersion": "lab/v1",
            "kind": "Dataset",
            "metadata": {
                "name": self.name,
                "version": self.version,
                "description": self.description,
            },
            "spec": spec,
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
            app=self.app,
        )

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[DatasetItem]:
        return iter(self.items)

    def __getitem__(self, idx: int) -> DatasetItem:
        return self.items[idx]
