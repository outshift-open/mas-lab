#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Declarative governance policy engine — mas-lab policy_engine port (kernel boundary)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mas.runtime.boundary.gov.exceptions import PolicySkip, PolicyViolation
from mas.runtime.schema.governance import GovernanceAction


class PolicyParseError(ValueError):
    """A declarative policy entry (overlay/agent-spec ``governance.policies``)
    is malformed — missing a required key, or naming a trigger point/action
    ``PolicyTrigger``/``PolicyDefinition`` doesn't recognize. Raised by
    :meth:`GovernancePolicyEngine.from_yaml` instead of letting the
    underlying ``KeyError``/``ValueError`` propagate raw, so a hand-edited
    overlay gets an actionable message naming the policy instead of an
    unexplained traceback."""


@dataclass
class PolicyTrigger:
    on: str
    tool: str = "*"
    condition: str = ""
    evaluation: str = "deterministic"
    threshold: int = 3
    reset_on: str = "success"

    VALID_TRIGGER_POINTS = frozenset(
        {
            "tool_input",
            "tool_output",
            "llm_output",
            "delegation_output",
            "budget_threshold",
            "event",
            "tool_failure_streak",
        }
    )

    def __post_init__(self) -> None:
        if self.on not in self.VALID_TRIGGER_POINTS:
            raise ValueError(f"invalid trigger point: {self.on!r}")


@dataclass
class PolicyDefinition:
    name: str
    trigger: PolicyTrigger
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    recovery: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    VALID_ACTIONS = frozenset(
        {"hitl", "block", "terminate", "log", "modify", "skip", "retry", "blacklist"}
    )

    def __post_init__(self) -> None:
        if self.action not in self.VALID_ACTIONS:
            raise ValueError(f"invalid action: {self.action!r}")


class ConditionEvaluator:
    _COMPARISON_RE = re.compile(
        r"^([\w.]+)\s*(>|<|>=|<=|==|!=|in|not\s+in|contains)\s*(.+)$"
    )

    @classmethod
    def evaluate(cls, condition: str, data: dict[str, Any]) -> bool:
        if not condition.strip():
            return True
        match = cls._COMPARISON_RE.match(condition.strip())
        if not match:
            return False
        path, op, raw_value = match.groups()
        left = cls._resolve_path(data, path)
        right = cls._parse_literal(raw_value.strip())
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "in":
            return left in right
        if op == "not in":
            return left not in right
        if op == "contains":
            return right in left
        return False

    @classmethod
    def _resolve_path(cls, data: dict[str, Any], path: str) -> Any:
        cur: Any = data
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    @classmethod
    def _parse_literal(cls, raw: str) -> Any:
        if raw in {"True", "False"}:
            return raw == "True"
        if raw == "None":
            return None
        if raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1]
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [cls._parse_literal(item.strip()) for item in inner.split(",")]
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            return raw


@dataclass
class GovernancePolicyEngine:
    policies: list[PolicyDefinition] = field(default_factory=list)
    tool_blacklist: set[str] = field(default_factory=set)
    failure_streaks: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, governance_config: dict[str, Any]) -> GovernancePolicyEngine:
        raw_policies = governance_config.get("policies", [])
        policies: list[PolicyDefinition] = []
        for index, item in enumerate(raw_policies):
            name = item.get("name") or f"#{index}"
            try:
                if not item.get("enabled", True):
                    continue
                trigger_raw = item["trigger"]
                policies.append(
                    PolicyDefinition(
                        name=item["name"],
                        trigger=PolicyTrigger(
                            on=trigger_raw["on"],
                            tool=trigger_raw.get("tool", "*"),
                            condition=trigger_raw.get("condition", ""),
                            evaluation=trigger_raw.get("evaluation", "deterministic"),
                            threshold=int(trigger_raw.get("threshold", 3)),
                            reset_on=trigger_raw.get("reset_on", "success"),
                        ),
                        action=item["action"],
                        params=item.get("params", {}),
                        recovery=item.get("recovery", {}),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise PolicyParseError(f"policy {name!r}: {exc}") from exc
        return cls(policies=policies)

    def evaluate_trigger(
        self,
        trigger_point: str,
        data: dict[str, Any],
        *,
        tool_name: str = "*",
    ) -> GovernanceAction | None:
        policy = self.find_matching_policy(trigger_point, data, tool_name=tool_name)
        return self.map_action(policy) if policy is not None else None

    def find_matching_policy(
        self,
        trigger_point: str,
        data: dict[str, Any],
        *,
        tool_name: str = "*",
    ) -> PolicyDefinition | None:
        """Same matching logic as ``evaluate_trigger``, but returns the policy
        itself (name, params) rather than just the mapped action — used to
        explain *why* a declarative decision fired (params.message/reason),
        without re-running the deterministic condition twice with different
        implementations that could silently drift apart."""
        for policy in self.policies:
            if not policy.enabled or policy.trigger.on != trigger_point:
                continue
            if policy.trigger.tool not in {"*", tool_name}:
                continue
            if policy.trigger.evaluation != "deterministic":
                continue
            if not ConditionEvaluator.evaluate(policy.trigger.condition, data):
                continue
            return policy
        return None

    def map_action(self, policy: PolicyDefinition) -> GovernanceAction:
        """Map a matched policy's declarative action string to a GovernanceAction.

        Public: callers outside this class (e.g. boundary/gov/policy.py, when
        explaining a decision alongside making it) need the same mapping
        ``evaluate_trigger``/``record_tool_failure`` use internally, rather than
        duplicating this table.
        """
        return {
            "hitl": GovernanceAction.HITL,
            "block": GovernanceAction.BLOCK,
            "terminate": GovernanceAction.TERMINATE,
            "log": GovernanceAction.LOG,
            "modify": GovernanceAction.MODIFY,
            "skip": GovernanceAction.SKIP,
            "retry": GovernanceAction.RETRY,
            "blacklist": GovernanceAction.BLACKLIST,
        }[policy.action]

    def apply_action(
        self,
        action: GovernanceAction,
        *,
        tool_name: str,
        policy_name: str = "declarative",
    ) -> None:
        if action == GovernanceAction.BLACKLIST:
            self.tool_blacklist.add(tool_name)
            raise PolicySkip(
                tool_name=tool_name,
                reason=f"blacklisted by {policy_name}",
            )
        if action == GovernanceAction.SKIP:
            raise PolicySkip(tool_name=tool_name, reason=f"skipped by {policy_name}")
        if action == GovernanceAction.BLOCK:
            raise PolicyViolation(f"blocked by {policy_name}", recoverable=True)
        if action == GovernanceAction.TERMINATE:
            raise PolicyViolation(f"terminated by {policy_name}", recoverable=False)

    def record_tool_failure(self, tool_name: str) -> GovernanceAction | None:
        self.failure_streaks[tool_name] = self.failure_streaks.get(tool_name, 0) + 1
        for policy in self.policies:
            if policy.trigger.on != "tool_failure_streak":
                continue
            if policy.trigger.tool not in {"*", tool_name}:
                continue
            if self.failure_streaks[tool_name] >= policy.trigger.threshold:
                return self.map_action(policy)
        return None

    def record_tool_success(self, tool_name: str) -> None:
        self.failure_streaks.pop(tool_name, None)

    def is_blacklisted(self, tool_name: str) -> bool:
        return tool_name in self.tool_blacklist
