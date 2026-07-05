#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve kernel + observability settings from merged manifests (spec-first)."""

from __future__ import annotations

from typing import Any

from mas.ctl.adapters.obs.config import ObservabilityConfig
from mas.ctl.manifest.spec_bindings import (
    normalize_obs_plugin,
    parse_governance,
    parse_observability,
    parse_sink_from_deployment,
)
from mas.ctl.session.governance_loader import build_governance_plugins
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.agent_defaults import default_pattern_plugin_id
from mas.runtime.schema.governance import GovPolicyProfile


# DEPRECATED: kernel_config_from_manifest is superseded by RuntimeInstance.from_spec()
# (runtime/src/mas/runtime/driver/instance.py). New callers should use from_spec() directly.
# This function is retained for backward compatibility and will be removed in a future release.
def kernel_config_from_manifest(
    manifest: dict | None,
    *,
    pattern_plugin_id: str | None = None,
) -> KernelConfig:
    spec = (manifest or {}).get("spec") or {}
    gov = parse_governance(spec.get("governance"))
    egress_plugin, gov_ingress_chain, _gov_flat = build_governance_plugins(
        plugin_names=list(gov.plugins),
        plugin_configs=dict(gov.plugin_configs),
    )
    if egress_plugin is None and (
        gov.hitl_on_tool or gov.hitl_on_tool_result or gov.gov_trigger_destructive
    ):
        from mas.runtime.boundary.gov.sample import SampleGovernancePlugin

        plugin_cfg = {
            k: v
            for k, v in {
                "hitl_on_tool": gov.hitl_on_tool,
                "hitl_on_tool_result": gov.hitl_on_tool_result,
                "hitl_once_per_turn": gov.hitl_once_per_turn,
                "gov_trigger_destructive": gov.gov_trigger_destructive,
                "gov_block_destructive": gov.gov_block_destructive,
                "gov_policy_profile": gov.gov_policy_profile,
            }.items()
            if v is not None
        }
        egress_plugin = SampleGovernancePlugin(**plugin_cfg)
        if egress_plugin.config.hitl_on_tool_result:
            from mas.runtime.boundary.gov.filter import GovTransitionFilter
            from mas.runtime.boundary.gov.ingress_chain import RegisteredIngressPlugin

            gov_ingress_chain = (
                RegisteredIngressPlugin(
                    plugin=egress_plugin,
                    filter=GovTransitionFilter(hook="ingress", response_kind=("TOOL_RESULT",)),
                    chain="stop",
                ),
            )
    kwargs: dict[str, Any] = {
        "pattern_plugin_id": pattern_plugin_id or default_pattern_plugin_id(),
    }
    if egress_plugin is not None:
        kwargs["egress_governance_plugin"] = egress_plugin
    if isinstance(gov.gov_policy_profile, str):
        kwargs["gov_policy_profile"] = GovPolicyProfile(gov.gov_policy_profile)
    for key, value in (
        ("gov_block_destructive", gov.gov_block_destructive),
        ("gov_trigger_destructive", gov.gov_trigger_destructive),
        ("hitl_on_tool", gov.hitl_on_tool),
        ("hitl_on_tool_result", gov.hitl_on_tool_result),
        ("hitl_once_per_turn", gov.hitl_once_per_turn),
        ("enable_memory_egress", gov.enable_memory_egress),
        ("enable_transport_egress", gov.enable_transport_egress),
        ("max_cot_pass", gov.max_cot_pass),
        ("max_gov_retries", gov.max_gov_retries),
    ):
        if value is not None:
            kwargs[key] = value
    if isinstance(gov.gov_ingress_profile, str):
        from mas.runtime.schema.governance import GovIngressProfile

        kwargs["gov_ingress_profile"] = GovIngressProfile(gov.gov_ingress_profile)
    from mas.ctl.session.ingress_governance_loader import build_ingress_governance_plugins

    chain = list(gov_ingress_chain) + list(
        build_ingress_governance_plugins(
            ingress_plugin_specs=list(gov.ingress_plugins),
            error_recovery_plugin=None,
        )
    )
    if chain:
        kwargs["ingress_governance_plugins"] = chain
        kwargs.pop("error_recovery_plugin", None)
    execution = spec.get("execution") or {}
    if "parallel" in execution:
        kwargs["parallel_tool_calls"] = bool(execution["parallel"])
    return KernelConfig(**kwargs)


def mas_id_from_manifest(manifest: dict | None) -> str:
    doc = manifest or {}
    kind = str(doc.get("kind") or "").lower()
    meta = doc.get("metadata") or {}
    if kind == "mas" and meta.get("name"):
        return str(meta["name"])
    mas = doc.get("mas") or {}
    if isinstance(mas, dict) and mas.get("name"):
        return str(mas["name"])
    if meta.get("mas_id"):
        return str(meta["mas_id"])
    return ""


def derive_observability_format(
    plugins: list[str],
    *,
    cli_override: str | None = None,
) -> str:
    """Derive export format from manifest plugin list and optional CLI override."""
    if cli_override:
        return cli_override
    has_native = "native" in plugins
    has_otel = "otel" in plugins
    if has_native and has_otel:
        return "both"
    if has_otel:
        return "otel"
    return "native"


def observability_config_from_manifest(
    manifest: dict | None,
    *,
    deployment: dict | None = None,
    agent_id: str = "agent",
    mas_id: str = "",
    cli_events: bool | None = None,
    cli_events_file: str | None = None,
    cli_events_stdout: bool = False,
    cli_events_format: str | None = None,
) -> ObservabilityConfig:
    """Spec / deployment first; CLI flags override when explicitly set."""
    spec = (manifest or {}).get("spec") or {}
    binding = parse_observability(spec.get("observability"))
    sink_ref = parse_sink_from_deployment(deployment)

    plugins = list(binding.plugins)
    if sink_ref and not plugins:
        plugins = [normalize_obs_plugin(sink_ref)]

    enabled = bool(plugins) or bool(sink_ref)
    if cli_events is not None:
        enabled = cli_events

    fmt = derive_observability_format(plugins, cli_override=cli_events_format)

    otel_cfg = binding.plugin_configs.get("otel") or {}
    otel_file = otel_cfg.get("otel_file")
    if not otel_file and otel_cfg.get("output_path"):
        from pathlib import Path

        otel_file = str(Path(str(otel_cfg["output_path"])) / "otel_sdk_spans.jsonl")

    events_file = cli_events_file or binding.events_file
    if not events_file:
        native_cfg = binding.plugin_configs.get("native") or {}
        events_file = native_cfg.get("path") or native_cfg.get("events_file")

    events_stdout = cli_events_stdout or binding.stdout

    return ObservabilityConfig(
        enabled=bool(enabled),
        format=str(fmt),
        events_file=str(events_file) if events_file else None,
        events_stdout=events_stdout,
        otel_file=str(otel_file) if otel_file else None,
        sink_ref=str(sink_ref) if sink_ref else None,
        agent_id=agent_id,
        mas_id=mas_id or mas_id_from_manifest(manifest),
        plugins=plugins,
        plugin_configs=dict(binding.plugin_configs),
    )


def engine_use_tool_loop(manifest: dict | None, kernel: KernelConfig) -> bool:
    """Whether the LLM engine exposes ``spec.tools`` for native function-calling.

    Structural only — not a manifest flag. ReAct (+ tools declared) ⇒ tool egress
    in the Mealy product; plan-execute schedules tools via the DP plugin instead.
    """
    if kernel.pattern_plugin_id == "plan_execute@v1":
        return False
    spec = (manifest or {}).get("spec") or {}
    return bool(spec.get("tools"))
