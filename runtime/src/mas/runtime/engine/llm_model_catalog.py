#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Versioned per-model LLM capability catalog.

The YAML is the data we would extract into a standalone library. Community
tables (LiteLLM, OpenRouter, …) are listed as sources, not vendored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CATALOG_PATH = Path(__file__).resolve().parents[1] / "spec" / "llm-model-catalog.yaml"
# Known models must advertise these; omitting one means unsupported.
_GATED_SETTINGS = frozenset(
    {
        "reasoning.effort",
        "reasoning.mode",
        "reasoning.exclude",
        "reasoning.budget_tokens",
        "think",
        "include",
    }
)


@dataclass(frozen=True)
class ModelSetting:
    supported: bool = True
    minimum: float | None = None
    maximum: float | None = None
    default: Any = None
    enum: tuple[Any, ...] | None = None

    def clamp(self, value: Any) -> Any:
        """Bound a numeric spec value to catalog min/max. Enum is documentation only."""
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return value
        out = float(value)
        if self.minimum is not None:
            out = max(out, self.minimum)
        if self.maximum is not None:
            out = min(out, self.maximum)
        return int(out) if isinstance(value, int) else out


@dataclass(frozen=True)
class ModelInfo:
    name: str
    aliases: tuple[str, ...] = ()
    context_window: int | None = None
    max_output_tokens: int | None = None
    max_thinking_tokens: int | None = None
    apis: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, ModelSetting] = field(default_factory=dict)

    def setting(self, name: str) -> ModelSetting | None:
        return self.settings.get(name)

    def supports(self, name: str) -> bool:
        spec = self.settings.get(name)
        if spec is not None:
            return spec.supported
        if name in _GATED_SETTINGS:
            return False
        return True

    def clamp(self, name: str, value: Any) -> Any:
        spec = self.settings.get(name)
        if spec is None:
            return value
        return spec.clamp(value)


@dataclass(frozen=True)
class ModelCatalog:
    version: str
    sources: tuple[dict[str, Any], ...]
    models: dict[str, ModelInfo]
    _alias_index: dict[str, str] = field(default_factory=dict)

    def get(self, model: str | None) -> ModelInfo | None:
        name = str(model or "").strip()
        if not name:
            return None
        if name in self.models:
            return self.models[name]
        mapped = self._alias_index.get(name) or self._alias_index.get(name.split("/")[-1])
        if mapped:
            return self.models.get(mapped)
        return None


def _parse_setting(raw: Any) -> ModelSetting:
    if not isinstance(raw, dict):
        return ModelSetting()
    enum = raw.get("enum")
    return ModelSetting(
        supported=raw.get("supported", True) is not False,
        minimum=float(raw["min"]) if raw.get("min") is not None else None,
        maximum=float(raw["max"]) if raw.get("max") is not None else None,
        default=raw.get("default"),
        enum=tuple(enum) if isinstance(enum, list) else None,
    )


def load_model_catalog(path: Path | None = None) -> ModelCatalog:
    target = path or _CATALOG_PATH
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    meta = data.get("metadata") or {}
    spec = data.get("spec") or {}
    models: dict[str, ModelInfo] = {}
    alias_index: dict[str, str] = {}
    raw_models = spec.get("models") or {}
    if isinstance(raw_models, dict):
        for name, raw in raw_models.items():
            if not isinstance(raw, dict):
                continue
            aliases = tuple(str(a) for a in (raw.get("aliases") or []) if a)
            settings_raw = raw.get("settings") or {}
            settings = {
                str(key): _parse_setting(value)
                for key, value in settings_raw.items()
                if isinstance(value, dict) or value is not None
            }
            info = ModelInfo(
                name=str(name),
                aliases=aliases,
                context_window=int(raw["context_window"]) if raw.get("context_window") else None,
                max_output_tokens=int(raw["max_output_tokens"]) if raw.get("max_output_tokens") else None,
                max_thinking_tokens=int(raw["max_thinking_tokens"]) if raw.get("max_thinking_tokens") is not None else None,
                apis=tuple(str(a) for a in (raw.get("apis") or [])),
                defaults=dict(raw.get("defaults") or {}),
                settings=settings,
            )
            models[info.name] = info
            alias_index[info.name] = info.name
            for alias in aliases:
                alias_index[alias] = info.name
    sources = tuple(s for s in (spec.get("sources") or []) if isinstance(s, dict))
    return ModelCatalog(
        version=str(meta.get("version") or ""),
        sources=sources,
        models=models,
        _alias_index=alias_index,
    )


@lru_cache(maxsize=1)
def default_model_catalog() -> ModelCatalog:
    return load_model_catalog()
