#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Simplified infra/v1 models for v2 ctl (aligned with mas-lab InfraManifest)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProxySpec:
    api_base: str = ""
    api_key_env: str = "OPENAI_API_KEY"


@dataclass
class ModelDefaults:
    llm: str | None = None
    embed: str | None = None


@dataclass
class ModelsSpec:
    allowed: list[str] = field(default_factory=list)
    default_llm: str | None = None
    default_embed: str | None = None
    mappings: dict[str, str] = field(default_factory=dict)

    @property
    def defaults(self) -> ModelDefaults:
        return ModelDefaults(llm=self.default_llm, embed=self.default_embed)

    def resolve(self, model: str) -> str:
        return self.mappings.get(model, model)


@dataclass
class InfraManifest:
    name: str = ""
    kind: str = ""
    proxy: ProxySpec = field(default_factory=ProxySpec)
    models: ModelsSpec = field(default_factory=ModelsSpec)
    model_access: dict[str, Any] = field(default_factory=dict)
    pipeline: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> InfraManifest:
        from mas.ctl.infra.env_resolve import resolve_manifest_values
        from mas.ctl.infra.resolve import _from_dict
        from mas.runtime.spec.source import load_yaml_file

        p = Path(path).resolve()
        data = load_yaml_file(p)
        if not isinstance(data, dict):
            raise ValueError(f"{p}: expected mapping")
        return _from_dict(resolve_manifest_values(data))

    @property
    def is_mock(self) -> bool:
        if self.model_access.get("provider") == "mock":
            return True
        if not self.proxy.api_base and self.kind in ("LLMLocal", "InfraBundle"):
            return bool(self.model_access)
        return False

    def to_llm_proxy_dict(self) -> dict[str, Any]:
        return {
            "api_base": self.proxy.api_base,
            "api_key_env": self.proxy.api_key_env,
            "default_model": self.models.default_llm,
            "mappings": dict(self.models.mappings),
            "allowed": list(self.models.allowed),
            "mock": self.is_mock,
            "model_access": dict(self.model_access),
            "pipeline": list(self.pipeline),
        }
