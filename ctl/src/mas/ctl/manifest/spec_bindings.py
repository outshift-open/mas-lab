#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Parse agent spec contract bindings — strict v2 shapes only.

Cardinality-one fields (scalar / single object): ``design_pattern``, ``llm``,
``memory``, ``execution``, ``mocking``.

Multi-cardinality fields (list): ``observability``, ``tools``, ``skills``,
``governance`` (plugin list — see governance-binding.schema.yaml).

Governance is a **plugin list** (like observability)::

    governance:
      - sample_governance:
          hitl_on_tool: true
          hitl_on_tool_result: true
          hitl_mode: interactive
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SpecBindingError(ValueError):
    """Manifest spec binding shape violates v2 contract."""


def normalize_obs_plugin(name: str) -> str:
    """Return trimmed plugin id — no aliases; runtime registry resolves implementations."""
    return (name or "").strip()


@dataclass(frozen=True)
class ObservabilityBinding:
    plugins: list[str] = field(default_factory=list)
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    otlp_endpoint_env: str | None = None
    trace_content: bool = True
    stdout: bool = False
    events_file: str | None = None


@dataclass(frozen=True)
class GovernanceBinding:
    """Governance plugin list + derived kernel fields."""

    plugins: list[str] = field(default_factory=list)
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    hitl_on_tool: bool | None = None
    hitl_on_tool_result: bool | None = None
    gov_policy_profile: str | None = None
    gov_block_destructive: bool | None = None
    gov_trigger_destructive: bool | None = None
    gov_ingress_profile: str | None = None
    enable_memory_egress: bool | None = None
    enable_transport_egress: bool | None = None
    max_cot_pass: int | None = None
    max_gov_retries: int | None = None
    hitl_mode: str | None = None
    hitl_once_per_turn: bool | None = None
    policies: list[dict[str, Any]] = field(default_factory=list)
    active_profile: str | None = None
    error_recovery_plugin: str | None = None
    ingress_plugins: list[dict[str, Any]] = field(default_factory=list)


def _parse_obs_list(items: list[Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    plugins: list[str] = []
    configs: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, str):
            plugins.append(normalize_obs_plugin(item))
        elif isinstance(item, dict):
            for raw_name, cfg in item.items():
                name = normalize_obs_plugin(str(raw_name))
                plugins.append(name)
                if isinstance(cfg, dict):
                    configs[name] = dict(cfg)
        else:
            raise SpecBindingError(
                f"observability list entries must be str or dict, got {type(item).__name__}"
            )
    return plugins, configs


def parse_observability(raw: Any) -> ObservabilityBinding:
    """Parse ``spec.observability`` — must be a list or absent."""
    if raw is None:
        return ObservabilityBinding(plugins=[])

    if not isinstance(raw, list):
        raise SpecBindingError(
            f"spec.observability must be a list, got {type(raw).__name__}"
        )

    plugins, configs = _parse_obs_list(raw)

    events_file: str | None = None
    for cfg in configs.values():
        if cfg.get("path"):
            events_file = str(cfg["path"])
            break
        if cfg.get("output_path"):
            events_file = str(cfg["output_path"])
            break

    return ObservabilityBinding(
        plugins=plugins,
        plugin_configs=configs,
        events_file=events_file,
    )


def _parse_gov_plugin_list(items: list[Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    plugins: list[str] = []
    configs: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, str):
            name = item.strip()
            plugins.append(name)
            configs.setdefault(name, {})
        elif isinstance(item, dict):
            for raw_name, cfg in item.items():
                name = str(raw_name).strip()
                plugins.append(name)
                if isinstance(cfg, dict):
                    configs[name] = dict(cfg)
                else:
                    configs[name] = {}
        else:
            raise SpecBindingError(
                f"governance list entries must be str or dict, got {type(item).__name__}"
            )
    return plugins, configs


def parse_governance(raw: Any) -> GovernanceBinding:
    """Parse ``spec.governance`` — plugin list only (see governance-binding.schema.yaml)."""
    if raw is None:
        return GovernanceBinding()

    if not isinstance(raw, list):
        raise SpecBindingError(
            f"spec.governance must be a plugin list, got {type(raw).__name__}. "
            "Wrap kernel fields in a plugin stanza, e.g. "
            "governance: [{sample_governance: {hitl_on_tool: true}}]"
        )

    plugins, configs = _parse_gov_plugin_list(raw)
    flat: dict[str, Any] = {}
    policies: list[dict[str, Any]] = []
    ingress_plugins: list[dict[str, Any]] = []
    for cfg in configs.values():
        for key, value in cfg.items():
            if key == "policies" and isinstance(value, list):
                policies.extend(p for p in value if isinstance(p, dict))
            elif key == "ingress_plugins" and isinstance(value, list):
                ingress_plugins.extend(p for p in value if isinstance(p, dict))
            elif key not in {"policies", "ingress_plugins", "profiles"}:
                flat.setdefault(key, value)
    return GovernanceBinding(
        plugins=plugins,
        plugin_configs=configs,
        hitl_on_tool=flat.get("hitl_on_tool"),
        hitl_on_tool_result=flat.get("hitl_on_tool_result"),
        gov_policy_profile=flat.get("gov_policy_profile"),
        gov_block_destructive=flat.get("gov_block_destructive"),
        gov_trigger_destructive=flat.get("gov_trigger_destructive"),
        gov_ingress_profile=flat.get("gov_ingress_profile"),
        enable_memory_egress=flat.get("enable_memory_egress"),
        enable_transport_egress=flat.get("enable_transport_egress"),
        max_cot_pass=flat.get("max_cot_pass"),
        max_gov_retries=flat.get("max_gov_retries"),
        hitl_mode=str(flat["hitl_mode"]) if flat.get("hitl_mode") is not None else None,
        hitl_once_per_turn=flat.get("hitl_once_per_turn"),
        policies=policies,
        active_profile=flat.get("active_profile"),
        error_recovery_plugin=(
            str(flat["error_recovery_plugin"])
            if flat.get("error_recovery_plugin") is not None
            else None
        ),
        ingress_plugins=ingress_plugins,
    )


_LLM_KEYS = frozenset({"model", "provider", "temperature", "max_tokens"})
_EXECUTION_KEYS = frozenset({"mocking", "cache", "parallel", "live", "timeout"})
_CONTROL_KEYS = frozenset({"budget", "circuit_breaker", "rate_limiter"})


def _reject_unknown_keys(raw: dict[str, Any], *, allowed: frozenset[str], field: str) -> None:
    for key in raw:
        if key not in allowed:
            raise SpecBindingError(f"{field}: unknown field {key!r}")


_DESIGN_PATTERN_KEYS = frozenset({"type", "ref", "params", "config"})
_COLLABORATION_KEYS = frozenset({"type", "ref", "params"})
_CONTEXT_MANAGER_KEYS = frozenset({"type", "ref", "params", "skills", "memory"})


def parse_design_pattern(raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise SpecBindingError(f"spec.design_pattern must be an object, got {type(raw).__name__}")
    _reject_unknown_keys(raw, allowed=_DESIGN_PATTERN_KEYS, field="spec.design_pattern")


def parse_collaboration(raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise SpecBindingError(f"spec.collaboration must be an object, got {type(raw).__name__}")
    _reject_unknown_keys(raw, allowed=_COLLABORATION_KEYS, field="spec.collaboration")


def parse_context_manager(raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise SpecBindingError(f"spec.context_manager must be an object, got {type(raw).__name__}")
    _reject_unknown_keys(raw, allowed=_CONTEXT_MANAGER_KEYS, field="spec.context_manager")


def parse_llm(raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise SpecBindingError(f"spec.llm must be an object, got {type(raw).__name__}")
    _reject_unknown_keys(raw, allowed=_LLM_KEYS, field="spec.llm")


def parse_execution(raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise SpecBindingError(f"spec.execution must be an object, got {type(raw).__name__}")
    _reject_unknown_keys(raw, allowed=_EXECUTION_KEYS, field="spec.execution")
    mocking = raw.get("mocking")
    if isinstance(mocking, dict):
        _reject_unknown_keys(mocking, allowed=frozenset({"enabled"}), field="spec.execution.mocking")
    cache = raw.get("cache")
    if isinstance(cache, dict):
        _reject_unknown_keys(cache, allowed=frozenset({"enabled"}), field="spec.execution.cache")


def parse_control(raw: Any) -> None:
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise SpecBindingError(f"spec.control must be an object, got {type(raw).__name__}")
    _reject_unknown_keys(raw, allowed=_CONTROL_KEYS, field="spec.control")


def parse_infra_lists(raw_spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Validate ``infra_refs`` and ``infra_interceptors`` list shapes."""
    refs_raw = raw_spec.get("infra_refs") or raw_spec.get("infra_ref")
    interceptors_raw = raw_spec.get("infra_interceptors") or raw_spec.get("infra_interceptor")
    refs = _as_str_list(refs_raw, field="spec.infra_refs")
    interceptors = _as_str_list(interceptors_raw, field="spec.infra_interceptors")
    return refs, interceptors


def _as_str_list(raw: Any, *, field: str) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        out: list[str] = []
        for i, item in enumerate(raw):
            if not isinstance(item, str) or not item.strip():
                raise SpecBindingError(f"{field}[{i}] must be a non-empty string")
            out.append(item.strip())
        return out
    raise SpecBindingError(f"{field} must be a string or list of strings")


def validate_agent_spec_bindings(spec: Any) -> None:
    """Reject unknown top-level spec keys that are not contract bindings."""
    if spec is None:
        return
    if not isinstance(spec, dict):
        raise SpecBindingError(f"spec must be an object, got {type(spec).__name__}")
    allowed = _AGENT_SPEC_KEYS
    for key in spec:
        if key.startswith("x-"):
            continue
        if key not in allowed:
            raise SpecBindingError(
                f"spec.{key}: not a recognized contract binding "
                "(see docs/design/spec-contract-bindings.md)"
            )
    if "governance" in spec:
        parse_governance(spec["governance"])
    if "observability" in spec:
        parse_observability(spec["observability"])
    if "llm" in spec:
        parse_llm(spec["llm"])
    if "execution" in spec:
        parse_execution(spec["execution"])
    if "control" in spec:
        parse_control(spec["control"])
    if "design_pattern" in spec:
        parse_design_pattern(spec["design_pattern"])
    if "collaboration" in spec:
        parse_collaboration(spec["collaboration"])
    if "context_manager" in spec:
        parse_context_manager(spec["context_manager"])
    parse_infra_lists(spec)


_AGENT_SPEC_KEYS = frozenset(
    {
        "context",
        "description",
        "intent",
        "role",
        "models",
        "model",
        "system_prompt",
        "tools",
        "skills",
        "tools_remove",
        "plugins",
        "memory",
        "memory_params",
        "memory_seed",
        "design_pattern",
        "capabilities",
        "delegation",
        "collaboration",
        "context_manager",
        "behavior",
        "governance",
        "llm",
        "execution",
        "control",
        "observability",
        "infra_refs",
        "infra_interceptors",
        "mocking",
        "params",
        "context_policy",
        "telemetry",
        "workflow",
        "agents",
        "tool_usage",
    }
)
