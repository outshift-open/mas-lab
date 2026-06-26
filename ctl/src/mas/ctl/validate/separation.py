#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Model/access separation rules — ported from mas-lab v1 validator step 3."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


def _is_set(val: Any) -> bool:
    return val is not None and val != "" and val is not False


def _iter_paths(obj: Any, prefix: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            yield from _iter_paths(v, p)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _iter_paths(item, f"{prefix}[{i}]")
    else:
        yield prefix, obj


class SeparationValidator(ABC):
    kind: ClassVar[str]

    @classmethod
    def collect_violations(cls, data: dict[str, Any]) -> list[str]:
        return cls._collect_violations(data)

    @classmethod
    @abstractmethod
    def _collect_violations(cls, data: dict[str, Any]) -> list[str]:
        ...


class AgentSeparationValidator(SeparationValidator):
    kind = "agent"

    @classmethod
    def _collect_violations(cls, data: dict[str, Any]) -> list[str]:
        spec = data.get("spec", {}) or {}
        models = spec.get("models", []) or []
        violations: list[str] = []
        for i, entry in enumerate(models):
            if not isinstance(entry, dict):
                continue
            if "api_base" in entry:
                violations.append(
                    f"spec.models[{i}].api_base is an access concern — move to workspace/CLI infra_refs"
                )
            if "api_key_env" in entry:
                violations.append(
                    f"spec.models[{i}].api_key_env is an access concern — move to workspace/CLI infra_refs"
                )
            if "provider" in entry:
                violations.append(
                    f"spec.models[{i}].provider is an access concern — remove from agent manifest"
                )

        if "system_prompt" in spec:
            violations.append(
                "spec.system_prompt is no longer valid — use spec.role.instructions or instructions_ref"
            )
        if "prompt_ref" in spec:
            violations.append("spec.prompt_ref is no longer valid — use spec.role.instructions_ref")

        role = spec.get("role", {}) or {}
        if isinstance(role, dict):
            has_inline = _is_set(role.get("instructions"))
            has_ref = _is_set(role.get("instructions_ref"))
            if has_inline and has_ref:
                violations.append(
                    "spec.role.instructions and spec.role.instructions_ref are mutually exclusive"
                )
        return violations


class FlavourSeparationValidator(SeparationValidator):
    kind = "flavour"

    @classmethod
    def _collect_violations(cls, data: dict[str, Any]) -> list[str]:
        spec = data.get("spec", {}) or {}
        llm = spec.get("llm", {}) or {}
        violations: list[str] = []
        if isinstance(llm, dict):
            if _is_set(llm.get("api_key")):
                violations.append(
                    "spec.llm.api_key contains a raw secret — use api_key_env for the env-var name"
                )
            if _is_set(llm.get("model")):
                violations.append("spec.llm.model belongs in kind: Agent (spec.models), not Flavour")
            if _is_set(llm.get("api_base")):
                violations.append(
                    "spec.llm.api_base belongs in infra/v1 LLMProxy, not in Flavour"
                )
        if spec.get("infra_refs"):
            violations.append("spec.infra_refs is forbidden in Flavour — use workspace or --infra-ref")
        if _is_set(spec.get("infra_ref")):
            violations.append("spec.infra_ref is forbidden in Flavour — use workspace or --infra-ref")
        return violations


class MASSeparationValidator(SeparationValidator):
    kind = "mas"
    _ACCESS_KEYS: ClassVar[frozenset[str]] = frozenset({"api_base", "api_key_env"})

    @classmethod
    def _collect_violations(cls, data: dict[str, Any]) -> list[str]:
        violations: list[str] = []
        for path, val in _iter_paths(data):
            # Inlined agents under agency are validated separately as kind: Agent.
            if path.startswith("spec.agency.agents["):
                continue
            key = path.rsplit(".", 1)[-1].split("[")[0]
            if key in cls._ACCESS_KEYS and _is_set(val):
                violations.append(f"{path} is an access concern — move to flavour/infra bundle")
            if key == "model" and _is_set(val):
                violations.append(f"{path} is model-selection — move to agent spec.models")
        return violations


class OverlaySeparationValidator(MASSeparationValidator):
    kind = "overlay"


class PlacementPlanSeparationValidator(SeparationValidator):
    """PlacementPlan must not carry agent logic or infra bind fields."""

    kind = "placement_plan"

    @classmethod
    def _collect_violations(cls, data: dict[str, Any]) -> list[str]:
        violations: list[str] = []
        spec = data.get("spec") or {}
        for agent in spec.get("agents") or []:
            if not isinstance(agent, dict):
                continue
            aid = agent.get("id", "?")
            if "runtime" in agent and isinstance(agent["runtime"], dict):
                if "pattern_plugin_id" in agent["runtime"]:
                    violations.append(
                        f"spec.agents[{aid!r}].runtime.pattern_plugin_id belongs in "
                        "EffectiveBind, not PlacementPlan"
                    )
            if "engine" in agent:
                violations.append(
                    f"spec.agents[{aid!r}].engine belongs in EffectiveBind (infra bind), not PlacementPlan"
                )
        text = str(data)
        if "pattern_plugin_id" in text and "PlacementPlan" in str(data.get("kind", "")):
            pass  # covered per-agent above
        return violations


_SEPARATION: dict[str, type[SeparationValidator]] = {
    "agent": AgentSeparationValidator,
    "flavour": FlavourSeparationValidator,
    "mas": MASSeparationValidator,
    "overlay": OverlaySeparationValidator,
    "patch": OverlaySeparationValidator,
    "placement_plan": PlacementPlanSeparationValidator,
}


def check_separation(data: dict[str, Any], kind: str | None) -> list[str]:
    if not kind:
        return []
    validator = _SEPARATION.get(kind.lower())
    if validator is None:
        return []
    return validator.collect_violations(data)
