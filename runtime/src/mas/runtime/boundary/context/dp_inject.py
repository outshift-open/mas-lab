#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Design-pattern context injection — TLA: ContextMachine.tla / M_ctx."""

from __future__ import annotations

from mas.runtime.registry import get_registry
from mas.runtime.kernel.state import QProduct


def inject_dp_protocol(
    injected: list[str],
    *,
    pattern_plugin_id: str,
    q: QProduct | None = None,
) -> list[str]:
    """Append pattern-specific protocol lines before context assembly completes."""
    try:
        plugin = get_registry().get_design_pattern(pattern_plugin_id)
    except KeyError:
        return injected
    lines_fn = getattr(plugin, "protocol_lines", None)
    if not callable(lines_fn):
        return injected
    extra = lines_fn(q)
    if not extra:
        return injected
    out = list(injected)
    out.extend(extra)
    return out
