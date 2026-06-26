#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve HITL adapters from declarative manifest governance (not CLI flags).

Architecture
------------
- **Kernel** emits ``EmitHitlRequest`` from ``M_gov`` egress gate only.
- **Interactive sessions** terminate HITL at the ctl surface (``OperatorConsole`` /
  curses TUI) — no in-process ``HitlTerminal`` on the controller.
- **Batch / pipe** sessions wire an in-process ``HitlResponder`` (auto-approve, etc.).
"""

from __future__ import annotations

from typing import Any

from mas.ctl.manifest.spec_bindings import parse_governance
from mas.runtime.boundary.hitl.responders import (
    AutoApproveResponder,
    AutoDenyResponder,
    HitlResponder,
)

_HITL_MODE_PLUGINS: dict[str, HitlResponder | None] = {
    "auto-approve": AutoApproveResponder(),
    "auto-deny": AutoDenyResponder(),
    "interactive": None,
}


def resolve_hitl_from_manifest(
    manifest: dict[str, Any] | None,
    *,
    session_interactive: bool = False,
) -> tuple[Any | None, Any | None]:
    """Return (hitl_responder, hitl_terminal) for SessionController / RuntimeBuilder.

    ``hitl_terminal`` is always ``None`` — interactive HITL is owned by ctl surfaces.
    """
    spec = (manifest or {}).get("spec") or {}
    gov = parse_governance(spec.get("governance"))
    if not gov.hitl_on_tool and not gov.hitl_on_tool_result:
        return None, None

    mode = (getattr(gov, "hitl_mode", None) or "interactive").strip().lower()
    if mode == "interactive" and not session_interactive:
        return AutoApproveResponder(), None
    responder = _HITL_MODE_PLUGINS.get(mode)
    if responder is None and mode != "interactive":
        raise ValueError(
            f"unsupported spec.governance.hitl_mode: {mode!r}; "
            f"expected one of {sorted(_HITL_MODE_PLUGINS)}"
        )
    return responder, None
