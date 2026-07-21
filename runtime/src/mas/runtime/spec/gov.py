#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pure spec parsers for agent governance — runtime-owned, no ctl dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SpecBindingError(ValueError):
    """Agent spec governance binding violates v2 contract."""


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


def _merge_gov_plugin_config(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge a second occurrence of the same plugin key (e.g. two stacked
    overlays both using ``sample_governance``) into the first.

    List-valued fields (``policies``, ``ingress_plugins``) concatenate — that
    is the whole point of stacking two overlays that each add policies, and a
    plain overwrite silently drops the first overlay's entire policy set.
    Scalar fields (``hitl_on_tool``, ``gov_policy_profile``, …) follow the
    same last-overlay-wins convention already used for every other config
    field this module merges.
    """
    merged = dict(existing)
    for key, value in new.items():
        prior = merged.get(key)
        if isinstance(prior, list) and isinstance(value, list):
            merged[key] = prior + value
        else:
            merged[key] = value
    return merged


def _parse_gov_plugin_list(
    items: list[Any],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
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
                new_cfg = dict(cfg) if isinstance(cfg, dict) else {}
                if name in configs:
                    configs[name] = _merge_gov_plugin_config(configs[name], new_cfg)
                else:
                    configs[name] = new_cfg
        else:
            raise SpecBindingError(
                f"governance list entries must be str or dict, got {type(item).__name__}"
            )
    return plugins, configs


def parse_gov_spec(raw: list | None) -> GovernanceBinding:
    """Parse ``spec.governance`` — plugin list only."""
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


def build_kernel_config(
    binding: GovernanceBinding,
    *,
    pattern_plugin_id: str = "",
) -> Any:
    """Instantiate governance plugins and build a KernelConfig from a GovernanceBinding.

    This is the runtime-owned counterpart to:
      - ctl/session/governance_loader.py::build_governance_plugins
      - ctl/session/manifest_config.py::kernel_config_from_manifest
    """
    from mas.runtime.boundary.gov.filter import GovTransitionFilter
    from mas.runtime.boundary.gov.ingress_chain import RegisteredIngressPlugin
    from mas.runtime.boundary.gov.policy_engine import GovernancePolicyEngine
    from mas.runtime.boundary.gov.sample import SampleGovernancePlugin
    from mas.runtime.kernel.config import KernelConfig
    from mas.runtime.agent_defaults import default_pattern_plugin_id
    from mas.runtime.schema.governance import GovIngressProfile, GovPolicyProfile

    egress_plugin: SampleGovernancePlugin | None = None
    ingress_entries: list[RegisteredIngressPlugin] = []

    import logging as _logging
    _gov_logger = _logging.getLogger(__name__)
    _KNOWN_GOV_PLUGINS = {"sample_governance", "sample_governance@v1"}

    for name in binding.plugins:
        cfg = dict(binding.plugin_configs.get(name) or {})
        if name in _KNOWN_GOV_PLUGINS:
            egress_plugin = SampleGovernancePlugin(**cfg)
            if egress_plugin.config.hitl_on_tool_result:
                ingress_entries.append(
                    RegisteredIngressPlugin(
                        plugin=egress_plugin,
                        filter=GovTransitionFilter(
                            hook="ingress", response_kind=("TOOL_RESULT",)
                        ),
                        chain="stop",
                    )
                )
        else:
            _gov_logger.warning(
                "governance plugin %r is not recognised by build_kernel_config "
                "(known: %s); it will be skipped",
                name, ", ".join(sorted(_KNOWN_GOV_PLUGINS)),
            )

    # Fallback: explicit flags without a named plugin
    if egress_plugin is None and (
        binding.hitl_on_tool or binding.hitl_on_tool_result or binding.gov_trigger_destructive
    ):
        plugin_cfg = {
            k: v
            for k, v in {
                "hitl_on_tool": binding.hitl_on_tool,
                "hitl_on_tool_result": binding.hitl_on_tool_result,
                "hitl_once_per_turn": binding.hitl_once_per_turn,
                "gov_trigger_destructive": binding.gov_trigger_destructive,
                "gov_block_destructive": binding.gov_block_destructive,
                "gov_policy_profile": binding.gov_policy_profile,
            }.items()
            if v is not None
        }
        egress_plugin = SampleGovernancePlugin(**plugin_cfg)
        if egress_plugin.config.hitl_on_tool_result:
            ingress_entries.append(
                RegisteredIngressPlugin(
                    plugin=egress_plugin,
                    filter=GovTransitionFilter(
                        hook="ingress", response_kind=("TOOL_RESULT",)
                    ),
                    chain="stop",
                )
            )

    kwargs: dict[str, Any] = {
        "pattern_plugin_id": pattern_plugin_id or default_pattern_plugin_id(),
    }
    if egress_plugin is not None:
        kwargs["egress_governance_plugin"] = egress_plugin
    if isinstance(binding.gov_policy_profile, str):
        kwargs["gov_policy_profile"] = GovPolicyProfile(binding.gov_policy_profile)
    for key, value in (
        ("gov_block_destructive", binding.gov_block_destructive),
        ("gov_trigger_destructive", binding.gov_trigger_destructive),
        ("hitl_on_tool", binding.hitl_on_tool),
        ("hitl_on_tool_result", binding.hitl_on_tool_result),
        ("hitl_once_per_turn", binding.hitl_once_per_turn),
        ("enable_memory_egress", binding.enable_memory_egress),
        ("enable_transport_egress", binding.enable_transport_egress),
        ("max_cot_pass", binding.max_cot_pass),
        ("max_gov_retries", binding.max_gov_retries),
    ):
        if value is not None:
            kwargs[key] = value
    if isinstance(binding.gov_ingress_profile, str):
        kwargs["gov_ingress_profile"] = GovIngressProfile(binding.gov_ingress_profile)

    if binding.policies:
        from mas.runtime.boundary.gov.policy_engine import PolicyParseError

        try:
            kwargs["policy_engine"] = GovernancePolicyEngine.from_yaml(
                {"policies": binding.policies}
            )
        except PolicyParseError as exc:
            raise SpecBindingError(f"spec.governance: {exc}") from exc

    # Build ingress chain (no ctl ingress loader needed at runtime level)
    chain = list(ingress_entries)
    if chain:
        kwargs["ingress_governance_plugins"] = chain

    # parallel_tool_calls is not part of GovernanceBinding; caller may set via spec.execution
    return KernelConfig(**kwargs)


__all__ = ["GovernanceBinding", "SpecBindingError", "build_kernel_config", "parse_gov_spec"]
