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

import os
from typing import Any

# ObservabilityBinding and GovernanceBinding now live in the runtime — import
# and re-export so all existing ctl importers continue to work unchanged.
from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.spec.gov import GovernanceBinding


class SpecBindingError(ValueError):
    """Manifest spec binding shape violates v2 contract."""


def normalize_obs_plugin(name: str) -> str:
    """Return trimmed plugin id — hyphens normalized to underscores."""
    return (name or "").strip().replace("-", "_")


def resolve_manifest_cfg_value(cfg: dict[str, Any], key: str, *, default: str = "") -> str:
    """Resolve a manifest config value from inline field or ``{key}_env`` reference."""
    direct = cfg.get(key)
    if direct is not None and str(direct).strip():
        return str(direct).strip()
    env_key = cfg.get(f"{key}_env")
    if env_key:
        return os.environ.get(str(env_key), default).strip()
    return default


def resolve_path_cfg(cfg: dict[str, Any]) -> str | None:
    """Resolve first non-empty path-like field (inline or env) from plugin config."""
    for key in ("path", "output_path", "events_file", "file_export_path"):
        val = resolve_manifest_cfg_value(cfg, key)
        if val:
            return val
    return None


def _resolve_path_cfg(cfg: dict[str, Any]) -> str | None:
    return resolve_path_cfg(cfg)



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
    otlp_endpoint_env: str | None = None
    for name, cfg in configs.items():
        path = _resolve_path_cfg(cfg)
        if path and name == "native" and not events_file:
            events_file = path
        if cfg.get("otlp_endpoint_env"):
            otlp_endpoint_env = str(cfg["otlp_endpoint_env"])
    if not otlp_endpoint_env:
        otlp_endpoint_env = "OTEL_EXPORTER_OTLP_ENDPOINT"

    return ObservabilityBinding(
        plugins=plugins,
        plugin_configs=configs,
        otlp_endpoint_env=otlp_endpoint_env,
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
    if raw.get("ref"):
        raise SpecBindingError(
            "spec.collaboration.ref is not supported in this release; omit spec.collaboration"
        )
    typ = raw.get("type")
    if isinstance(typ, str) and typ.strip() and typ.strip().lower() != "none":
        raise SpecBindingError(
            f"spec.collaboration.type {typ.strip()!r} is not supported in this release; "
            "omit spec.collaboration or set type: none"
        )


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
    """Validate shapes of present contract bindings (schema defines allowed keys)."""
    if spec is None:
        return
    if not isinstance(spec, dict):
        raise SpecBindingError(f"spec must be an object, got {type(spec).__name__}")
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


def parse_sink_from_deployment(deployment: dict | None) -> str | None:
    """Extract observability sink/backend ref from a deployment manifest."""
    if not deployment:
        return None
    spec = deployment.get("spec") or {}
    shared = spec.get("shared") or {}
    if isinstance(shared, dict):
        ref = shared.get("observability_ref") or shared.get("sink_ref")
        if ref:
            return str(ref)
    obs = spec.get("observability") or {}
    if isinstance(obs, dict):
        return obs.get("backend") or obs.get("sink_ref")
    return None
