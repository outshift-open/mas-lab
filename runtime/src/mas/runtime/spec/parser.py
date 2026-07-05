#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Top-level helper: parse a raw agent spec dict into runtime-ready objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mas.runtime.spec.gov import GovernanceBinding, build_kernel_config, parse_gov_spec
from mas.runtime.spec.obs import parse_obs_spec

if TYPE_CHECKING:
    from mas.runtime.boundary.obs.binding import ObservabilityBinding
    from mas.runtime.kernel.config import KernelConfig


def _resolve_pattern_plugin_id(spec: dict[str, Any]) -> str:
    """Resolve ``spec.design_pattern`` to a pattern plugin id string."""
    from mas.runtime.agent_defaults import default_pattern_plugin_id
    from mas.runtime.registry import get_registry

    dp_raw = spec.get("design_pattern")
    if not dp_raw:
        return default_pattern_plugin_id()

    binding = dp_raw if isinstance(dp_raw, dict) else {}
    name = str(binding.get("type") or binding.get("ref") or "").strip()
    if not name:
        return default_pattern_plugin_id()

    reg = get_registry()
    info = reg.resolve_by_type("design_pattern", name)
    if info is None:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "design_pattern %r not found in registry; passing through to kernel", name
        )
    return name


def parse_agent_spec(
    spec: dict[str, Any],
) -> tuple[KernelConfig, ObservabilityBinding | None]:
    """Parse a raw agent spec dict into (KernelConfig, ObservabilityBinding | None).

    ``spec`` is the inner ``spec:`` block from an agent manifest, e.g.::

        manifest["spec"]

    Returns a tuple of:
    - ``KernelConfig`` built from governance spec + design pattern
    - ``ObservabilityBinding | None`` (None when observability is absent/empty)
    """
    gov_raw = spec.get("governance")
    obs_raw = spec.get("observability")
    execution = spec.get("execution") or {}

    gov_binding: GovernanceBinding = parse_gov_spec(gov_raw)
    pattern_plugin_id = _resolve_pattern_plugin_id(spec)

    kernel_config = build_kernel_config(gov_binding, pattern_plugin_id=pattern_plugin_id)

    # Apply spec.execution.parallel override
    if "parallel" in execution:
        from dataclasses import replace

        kernel_config = replace(
            kernel_config,
            parallel_tool_calls=bool(execution["parallel"]),
        )

    obs_binding = parse_obs_spec(obs_raw)
    obs_result: ObservabilityBinding | None = obs_binding if obs_binding.plugins else None

    return kernel_config, obs_result


__all__ = ["parse_agent_spec"]
