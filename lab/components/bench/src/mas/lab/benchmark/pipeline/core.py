#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""
Pipeline step base classes and YAML pipeline loader.
"""


import asyncio
import inspect
import warnings as _warnings_module
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union

import yaml

from mas.lab.benchmark.pipeline.models import (
    _STEP_KNOWN_KEYS,
    ConfigParam,
    PipelineConfig,
    StepManifest,
    StepOutput,
)
from mas.lab.benchmark.pipeline.registry import _resolve_step_class


class PipelineStep(ABC):
    """Base class for pipeline steps."""

    type: str = "base"
    persistent: bool = False
    PARAMS: ClassVar[List[ConfigParam]] = []

    def __init__(
        self,
        name: str,
        config: Dict[str, Any],
        depends_on: Optional[List[str]] = None,
        phase: str = "post",
    ):
        self.name = name
        self.config = config
        self.depends_on = depends_on or []
        self.phase = phase

    def is_persistent(self) -> bool:
        cfg_val = self.config.get("persist")
        if cfg_val is not None:
            return bool(cfg_val)
        return getattr(self.__class__, "persistent", True)

    @abstractmethod
    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        pass

    def outputs_exist(self, output_dir: Path) -> bool:
        return True

    @property
    def output_artifacts(self) -> List[Tuple[str, Any]]:
        return []

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Optional[Path] = None) -> PipelineStep:
        step_type = data["type"]
        step_class = _resolve_step_class(step_type, base_dir=base_dir)

        unknown_keys = {
            k for k in data.keys() if k not in _STEP_KNOWN_KEYS and not k.startswith("x-")
        }
        if unknown_keys:
            _warnings_module.warn(
                f"Step {data.get('name', '?')!r}: unknown key(s) {sorted(unknown_keys)!r} "
                f"in pipeline YAML.  Did you mean to put them under 'config:'?",
                stacklevel=2,
            )

        cfg = dict(data.get("config", {}))
        if step_type == "processor" and "processor" in data:
            cfg.setdefault("processor", data["processor"])

        return step_class(
            name=data["name"],
            config=cfg,
            depends_on=data.get("depends_on", []),
            phase=data.get("phase", "post"),
        )

    @classmethod
    def manifest(cls) -> Optional[StepManifest]:
        src_file = inspect.getfile(cls)
        manifest_file = Path(src_file).with_suffix(".yaml")
        if manifest_file.exists():
            return StepManifest.from_yaml(manifest_file)
        return None


class BatchPipelineStep(PipelineStep, ABC):
    """Base class for steps that process a collection of items independently."""

    @abstractmethod
    async def process_one(
        self,
        item: Any,
        ctx: "ExecutionContext",
    ) -> StepOutput:
        pass

    def _get_items(self, ctx: "ExecutionContext") -> List[Any]:
        items = self.config.get("items", [])
        if not items:
            raise ValueError(
                f"Step '{self.name}': no 'items' in config.  "
                "Override _get_items() or provide config.items."
            )
        return items

    def _merge_results(
        self,
        items: List[Any],
        results: List[StepOutput],
        ctx: "ExecutionContext",
    ) -> StepOutput:
        all_files: List[Path] = []
        all_data: List[Dict[str, Any]] = []
        all_meta: List[Dict[str, Any]] = []
        for so in results:
            all_files.extend(so.files)
            all_data.append(so.data)
            all_meta.append(so.metadata)
        return StepOutput(
            data={"results": all_data, "items": items},
            files=all_files,
            metadata={"item_count": len(items), "results": all_meta},
        )

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        items = self._get_items(ctx)
        concurrency = int(self.config.get("concurrency", 1))

        if concurrency > 1:
            sem = asyncio.Semaphore(concurrency)

            async def _bounded(item: Any) -> StepOutput:
                async with sem:
                    return await self.process_one(item, ctx)

            results = await asyncio.gather(*[_bounded(item) for item in items])
        else:
            results = []
            for item in items:
                results.append(await self.process_one(item, ctx))

        return self._merge_results(items, list(results), ctx)


class YAMLIncludeLoader(yaml.SafeLoader):
    """Custom YAML loader with !include support."""

    def __init__(self, stream):
        self._root = Path(stream.name).parent if hasattr(stream, "name") else Path.cwd()
        super().__init__(stream)


def include_constructor(loader: YAMLIncludeLoader, node: yaml.Node) -> Any:
    path = loader.construct_scalar(node)
    include_path = loader._root / path

    with open(include_path, "r") as f:
        return yaml.load(f, YAMLIncludeLoader)


YAMLIncludeLoader.add_constructor("!include", include_constructor)


class Pipeline:
    """Declarative pipeline with dependency tracking."""

    def __init__(
        self,
        config: PipelineConfig,
        steps: List[PipelineStep],
        config_path: Optional[Path] = None,
    ):
        self.config = config
        self.steps = steps
        self.config_path = config_path
        self._step_map = {step.name: step for step in steps}
        self._validate()

    def _validate(self):
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            raise ValueError(f"Duplicate step names: {duplicates}")

        for step in self.steps:
            for dep in step.depends_on:
                if dep not in self._step_map:
                    raise ValueError(
                        f"Step '{step.name}' depends on unknown step '{dep}'"
                    )

        from mas.lab.benchmark.pipeline.resolver import DependencyResolver

        resolver = DependencyResolver(self)
        try:
            resolver.resolve()
        except ValueError as e:
            raise ValueError(f"Pipeline validation failed: {e}") from e

    def get_step(self, name: str) -> Optional[PipelineStep]:
        return self._step_map.get(name)

    def get_dependencies(self, step_name: str) -> List[PipelineStep]:
        step = self.get_step(step_name)
        if not step:
            return []
        return [self._step_map[dep] for dep in step.depends_on if dep in self._step_map]

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> Pipeline:
        path = Path(path)

        with open(path, "r") as f:
            raw = yaml.load(f, YAMLIncludeLoader)

        from mas.lab.manifests import normalize_manifest_version

        data, _manifest_version = normalize_manifest_version(raw, "pipeline", path)

        pipeline_data = data.get("pipeline", data)

        if "spec" in pipeline_data and "metadata" in pipeline_data:
            meta = pipeline_data.get("metadata", {})
            spec = pipeline_data.get("spec", {})
            pipeline_data = {
                "name": meta.get("name", ""),
                "description": meta.get("description", ""),
                **spec,
            }

        config = PipelineConfig.from_dict(pipeline_data)
        steps = [
            PipelineStep.from_dict(step_data)
            for step_data in pipeline_data.get("steps", [])
        ]

        return cls(config=config, steps=steps, config_path=path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline": {
                "name": self.config.name,
                "version": self.config.version,
                "description": self.config.description,
                "output": self.config.output,
                "steps": [
                    {
                        "name": step.name,
                        "type": step.type,
                        "depends_on": step.depends_on,
                        "config": step.config,
                    }
                    for step in self.steps
                ],
            }
        }


__all__ = [
    "PipelineStep",
    "BatchPipelineStep",
    "YAMLIncludeLoader",
    "include_constructor",
    "Pipeline",
]
