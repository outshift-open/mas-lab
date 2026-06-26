#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Transition filters for governance plugins — same vocabulary as observability attribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from mas.runtime.boundary.gov.ingress_plugin import IngressIntentView
from mas.runtime.boundary.gov.policy import EgressIntentView


@dataclass(frozen=True)
class GovTransitionFilter:
    """When empty, matches all transitions on the declared hook."""

    hook: Literal["ingress", "egress"] = "ingress"
    response_kind: tuple[str, ...] = ()
    op: tuple[str, ...] = ()
    destructive: bool | None = None
    machine: tuple[str, ...] = ()  # M_model, M_tool, …

    @classmethod
    def from_dict(cls, raw: dict) -> GovTransitionFilter:
        hook = str(raw.get("hook") or "ingress")
        if hook not in {"ingress", "egress"}:
            hook = "ingress"

        def _tuple(key: str) -> tuple[str, ...]:
            val = raw.get(key)
            if val is None:
                return ()
            if isinstance(val, str):
                return (val,)
            if isinstance(val, list):
                return tuple(str(x) for x in val)
            return ()

        destructive = raw.get("destructive")
        return cls(
            hook=hook,  # type: ignore[arg-type]
            response_kind=_tuple("response_kind"),
            op=_tuple("op"),
            machine=_tuple("machine"),
            destructive=bool(destructive) if destructive is not None else None,
        )

    def matches_ingress(self, intent: IngressIntentView) -> bool:
        if self.hook != "ingress":
            return False
        if self.response_kind and intent.response_kind not in self.response_kind:
            return False
        return True

    def matches_egress(self, intent: EgressIntentView) -> bool:
        if self.hook != "egress":
            return False
        if self.op and intent.op not in self.op:
            return False
        if self.destructive is not None and intent.destructive != self.destructive:
            return False
        if self.op == ("TOOL_CALL",) or (not self.op and intent.op == "TOOL_CALL"):
            if self.machine and "M_tool" not in self.machine:
                return False
        if intent.op == "LLM_CALL" and self.machine and "M_model" not in self.machine:
            if self.machine:  # machine filter set but not M_model
                return False
        return True
