#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class UISpec:
    """Demo-specific UI configuration hints.

    Attributes
    ----------
    port:
        HTTP port for the demo UI server.  ``None`` means "use the CLI
        ``--port`` argument" (i.e. not explicitly set in lab-config.yaml).
    mode:
        ``"interactive"`` (user drives) or ``"automated"`` (runs without input).
    layout:
        Graph layout hint for the topology visualiser (``"dag"``, ``"grid"``, ``"default"``).
    node_positions:
        Optional per-agent canvas coordinates ``{agent_id: {x: float, y: float}}``.
        When provided, the UI pins agents at these positions instead of auto-laying them out.
    """

    port: Optional[int] = None
    mode: str = "interactive"
    layout: str = "default"
    node_positions: Dict[str, Dict[str, float]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UISpec":
        return cls(
            port=data.get("port"),  # None when absent — caller falls back to CLI --port
            mode=data.get("mode", "interactive"),
            layout=data.get("layout", "default"),
            node_positions=data.get("node_positions", {}),
        )

