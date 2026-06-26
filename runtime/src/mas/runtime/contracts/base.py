#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# LAYER: L3 — Contract Layer  (OS analogue: POSIX ABI / Syscall Interface)
# -------------------------------------------------------------------
# Contracts are the stable interface between L2 (Hook Bus) and L4 (Plugins).
# A governance plugin at L4 is written against a Contract, not a backend.
# Liskov Substitution must hold: any Contract implementation is substitutable
# without changing the governance properties that depend on it.
# Reference: §16.1 (Layer 3) in formal_governance_and_ops.md
# -------------------------------------------------------------------
"""Contract taxonomy base classes and registry.

This module defines the two-level contract taxonomy used across the
mas-runtime and establishes a lightweight auto-registration mechanism so
that the runtime can inspect, validate, and compose contracts at load time.

Contract taxonomy
─────────────────

    ContractBase (abstract)
    ├── CapabilityContract      — WHAT the agent can access
    │   ├── ToolContract         (tool execution boundary)
    │   ├── PromptContract       (prompt template fetching)
    │   ├── MemoryContract       (memory read/write)
    │   ├── SensorContract       (inbound signal boundary)
    │   ├── SessionContract      (durable session state)
    │   ├── TransportContract    (inter-agent messaging)
    │   ├── MessageContract      (simple message send)
    │   ├── RecorderContract     (telemetry emit)
    │   ├── ControlContract      (pause/resume/abort/steer)
    │   ├── SharedContextContract(shared state coordination)
    │   ├── DelegationContract   (agent-as-tool)
    │   ├── ModelAccessContract  (model selection/routing)
    │   ├── ContextContract      (prompt assembly)
    │   ├── LLMContract          (direct LLM call)
    │   └── DesignPatternContract(reasoning pattern realizability)
    │
    ├── OrchestrationContract   — HOW control flows between agents
    │   └── MainLoopContract     (execution topology: single-shot, supervisor loop…)
    │
    └── GovernanceContract      — POLICY over capabilities
        ├── BudgetContract       (token / cost / call-rate ceilings)
        └── RoutingContract      (topology / edge policy)        ← future
        # SandboxContract, TBACContract — internal-only (mas-lab-internal)

Key distinctions
────────────────
CapabilityContract:
  - Defines a resource boundary (what can be called)
  - Plugins IMPLEMENT it to provide a capability
  - The agent CONSUMES it via the contract interface

GovernanceContract:
  - Defines a policy boundary (what is allowed)
  - Applied by the runtime BEFORE and AFTER capability contracts fire
  - Raises ``PolicyViolation`` to deny; never returns "allowed" explicitly
  - ORTHOGONAL to capability contracts — can be added/removed without
    changing the capability topology

Petri net vs GovernanceContract
────────────────────────────────
Petri net token-place rate limits control FLOW (back-pressure, concurrency —
how many firings per time window; tokens are restored after each firing).

GovernanceContract controls RESOURCE ACCOUNTING (cumulative consumption over
the lifetime of a run; counters are monotonically decreasing and never reset).

Both are necessary and orthogonal:
  • Petri net: prevents thundering-herd / deadlock (structural)
  • GovernanceContract: prevents cost explosion / data exfiltration (economic)

See §28 of formal_governance_and_ops.md for the full formal treatment.

Plugin dependency metadata
──────────────────────────
Every plugin declares its contract relationships via class variables:

    class MyPlugin(BasePlugin):
        plugin_id    = "my_plugin@v1"
        implements   = ["tool"]           # contracts this plugin fulfills
        requires     = ["recorder"]       # contracts this plugin needs injected
        governed_by  = ["budget"]  # governance contracts applied

The runtime uses these to:
  1. Validate that all required contracts are wired before execution
  2. Auto-attach governance plugins to the correct hooks
  3. Generate dependency graphs for ops dashboards

Contract registry
─────────────────
Contracts auto-register via ``__init_subclass__``.  Query the registry:

    ContractRegistry.get("tool")       → ToolContract class
    ContractRegistry.all_capability()  → list of CapabilityContract subclasses
    ContractRegistry.all_governance()  → list of GovernanceContract subclasses
"""

from abc import ABC
import re as _re
from typing import Any, ClassVar, Dict, List, Optional, Type


# ---------------------------------------------------------------------------
# @plugin decorator  (L3 — zero-ceremony plugin declaration)
# ---------------------------------------------------------------------------

def plugin(cls=None, *, plugin_id: Optional[str] = None,
           requires: Optional[List[str]] = None,
           governed_by: Optional[List[str]] = None):
    """Class decorator that auto-infers plugin metadata from the MRO.

    Removes the need for boilerplate ClassVars.  Usage::

        @plugin
        class MyTool(ToolContract):
            def get_name(self): return "my-tool"
            def execute(self, **kw): ...

        # Or with explicit overrides:
        @plugin(requires=["recorder"], governed_by=["budget"])
        class MyTool(ToolContract): ...

    What it infers:
    - ``plugin_id``: snake_case of class name + ``@v1`` (if not set)
    - ``implements``: walks MRO to find parent classes that have a
      non-None ``contract_id``; collects those IDs automatically
    """
    def _apply(cls):
        # --- plugin_id: auto-generate from class name if absent ---
        if not cls.__dict__.get("plugin_id"):
            name = cls.__name__
            # CamelCase → snake_case
            snake = _re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
            snake = _re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", snake).lower()
            # Strip trailing _plugin / _tool suffixes for cleaner IDs
            for suffix in ("_plugin", "_tool"):
                if snake.endswith(suffix):
                    snake = snake[: -len(suffix)]
                    break
            cls.plugin_id = f"{snake}@v1"

        # --- implements: infer from contract hierarchy ---
        if not cls.__dict__.get("implements"):
            inferred = []
            for base in cls.__mro__:
                cid = base.__dict__.get("contract_id")
                if cid and cid not in inferred:
                    inferred.append(cid)
            if inferred:
                cls.implements = inferred

        # --- requires / governed_by: apply if given ---
        if requires is not None:
            cls.requires = requires
        if governed_by is not None:
            cls.governed_by = governed_by

        return cls

    if cls is not None:
        # Called as @plugin without arguments
        return _apply(cls)
    # Called as @plugin(...) with keyword arguments
    return _apply


# ---------------------------------------------------------------------------
# BasePlugin  (L3 — plugin attachment protocol)
# ---------------------------------------------------------------------------
# DESIGN INTENT
# ───────────
# BasePlugin lives at L3 so that CapabilityContracts and GovernanceContracts
# can inherit from it without creating an upward dependency into L4 (Plugins).
#
# What belongs here (L3):
#   • Plugin metadata ClassVars (plugin_id, implements, requires, governed_by)
#   • attach_agent() — lightweight agent attachment (agent_id + config only)
#
# What does NOT belong here (L4 only):
#   • PluginRegistry auto-registration — lives in L4 _RegistryMixin
#     (core_plugins.py) so that L3 never imports from L4.
#   • Hook execution methods — belong on TypeA–TypeE base classes in L4.
# ---------------------------------------------------------------------------

class BasePlugin:
    """Base plugin attachment protocol — L3 Contract Layer.

    Provides plugin metadata ClassVars and a lightweight ``attach_agent``
    method.  Auto-registration into ``PluginRegistry`` (L4) is intentionally
    absent here to preserve the L3 → L2 dependency direction.  Registration
    is added by the L4 ``_RegistryMixin`` that all TypeA–TypeE plugin bases
    inherit from.

    Class variables (declare in subclasses):

    ``plugin_id`` : str
        Unique identifier, e.g. ``"budget_plugin@v1"``.  When a subclass
        inheriting from a TypeA–TypeE base (L4) declares this, the plugin
        auto-registers into ``PluginRegistry``.

    ``implements`` : List[str]
        Contract IDs this plugin fulfills, e.g. ``["tool", "prompt"]``.

    ``requires`` : List[str]
        Contract IDs this plugin needs injected, e.g. ``["recorder"]``.

    ``governed_by`` : List[str]
        Governance contract IDs applied to this plugin's operations,
        e.g. ``["budget", "sandbox"]``.
    """

    plugin_id:   ClassVar[Optional[str]]  = None
    implements:  ClassVar[List[str]]      = []
    requires:    ClassVar[List[str]]      = []
    governed_by: ClassVar[List[str]]      = []

    def attach_agent(self, agent: Any) -> None:
        """Attach agent metadata (agent_id, config) to this plugin instance.

        Safe to override in subclasses.  Do NOT pull ``recorder``, ``registry``,
        or other capability objects here — declare them via ``requires`` instead
        and inject them through the plugin chain.
        """
        self.agent = agent
        self.config = getattr(agent, "config", {})
        self.agent_id = getattr(agent, "agent_id", "unknown")


# ---------------------------------------------------------------------------
# Policy exception
# ---------------------------------------------------------------------------

class PolicyViolation(Exception):
    """Raised by a GovernanceContract when a request violates policy.

    Attributes
    ----------
    contract_id : str
        The contract that raised the violation.
    reason : str
        Human-readable explanation.
    details : dict
        Machine-readable context for audit logging.
    """

    def __init__(
        self,
        contract_id: str,
        reason: str,
        details: Optional[Dict] = None,
    ) -> None:
        self.contract_id = contract_id
        self.reason = reason
        self.details = details or {}
        super().__init__(f"[{contract_id}] PolicyViolation: {reason}")


# ---------------------------------------------------------------------------
# Contract registry
# ---------------------------------------------------------------------------

class ContractRegistry:
    """Central registry of all contract classes.

    Contracts register themselves automatically via ``ContractBase.__init_subclass__``.
    The runtime uses this registry to:
    - Validate plugin dependency declarations at startup
    - Generate contract dependency graphs
    - Auto-wire governance contracts to the appropriate hooks

    Do not instantiate — all methods are class-level.
    """

    _registry: ClassVar[Dict[str, Type["ContractBase"]]] = {}

    @classmethod
    def register(cls, contract_id: str, contract_cls: Type["ContractBase"]) -> None:
        """Explicitly register a contract class under a canonical ID."""
        if contract_id in cls._registry and cls._registry[contract_id] is not contract_cls:
            # Allow re-registration of same class (e.g. module reload); log on override
            import logging
            logging.getLogger(__name__).debug(
                "ContractRegistry: overriding '%s' (%s → %s)",
                contract_id,
                cls._registry[contract_id].__name__,
                contract_cls.__name__,
            )
        cls._registry[contract_id] = contract_cls

    @classmethod
    def get(cls, contract_id: str) -> Optional[Type["ContractBase"]]:
        """Return the contract class for a given ID, or None."""
        return cls._registry.get(contract_id)

    @classmethod
    def require(cls, contract_id: str) -> Type["ContractBase"]:
        """Return the contract class or raise KeyError."""
        if contract_id not in cls._registry:
            raise KeyError(
                f"Contract '{contract_id}' is not registered. "
                f"Known contracts: {sorted(cls._registry)}"
            )
        return cls._registry[contract_id]

    @classmethod
    def all_capability(cls) -> List[Type["CapabilityContract"]]:
        """Return all registered CapabilityContract subclasses."""
        return [c for c in cls._registry.values() if issubclass(c, CapabilityContract)]

    @classmethod
    def all_governance(cls) -> List[Type["GovernanceContract"]]:
        """Return all registered GovernanceContract subclasses."""
        return [c for c in cls._registry.values() if issubclass(c, GovernanceContract)]

    @classmethod
    def summary(cls) -> Dict[str, str]:
        """Return {contract_id: contract_type_label} for diagnostics."""
        result = {}
        for cid, ccls in sorted(cls._registry.items()):
            if issubclass(ccls, GovernanceContract):
                label = "governance"
            elif issubclass(ccls, CapabilityContract):
                label = "capability"
            elif issubclass(ccls, OrchestrationContract):
                label = "orchestration"
            else:
                label = "base"
            result[cid] = label
        return result


# ---------------------------------------------------------------------------
# ContractBase
# ---------------------------------------------------------------------------

class ContractBase(ABC):
    """Abstract root of the contract taxonomy.

    All contracts must declare a ``contract_id`` class variable. This ID is
    used by the plugin metadata system (``BasePlugin.implements``,
    ``BasePlugin.requires``) and by the ``ContractRegistry``.

    Subclasses auto-register into ``ContractRegistry`` when their
    ``contract_id`` is non-None and non-empty.
    """

    contract_id: ClassVar[Optional[str]] = None  # e.g. "tool", "budget", "sensor"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Use cls.__dict__ (not getattr) to avoid registering subclasses that
        # merely INHERIT contract_id from a parent without overriding it.
        # e.g. LocalTBACPlugin inherits contract_id="tbac" from TBACContract
        # but should NOT re-register under "tbac" (that would overwrite it).
        cid = cls.__dict__.get("contract_id")
        if cid and not str(cid).startswith("_"):
            ContractRegistry.register(cid, cls)


# ---------------------------------------------------------------------------
# CapabilityContract
# ---------------------------------------------------------------------------

class CapabilityContract(ContractBase, BasePlugin):
    """Base for contracts that define a CAPABILITY boundary.

    Inherits from both ``ContractBase`` (contract_id auto-registration into
    ``ContractRegistry``) and ``BasePlugin`` (attach_agent, plugin metadata
    ClassVars).  All capability contract classes should inherit from this
    rather than directly from ``BasePlugin``.

    A capability contract describes WHAT the agent can access.  Plugins
    implement it to expose a resource.  The agent consumes it through the
    interface methods.

    Characteristic properties:
    - Has input/output methods (call_tool, pull, send, emit, …)
    - Raises domain exceptions on failure (ToolError, TransportError, …)
    - Does NOT enforce policy — it delegates that to GovernanceContract layers
    - Tested for correctness via validate_* helpers

    Lifecycle hook involvement:
    - Methods fire pre_* / post_* hooks at their execution boundary
    - The runtime assembles hook chains from plugin registrations
    """

    contract_id: ClassVar[Optional[str]] = None


# ---------------------------------------------------------------------------
# OrchestrationContract
# ---------------------------------------------------------------------------

class OrchestrationContract(ContractBase):
    """Base for contracts that define CONTROL FLOW over the agent/MAS topology.

    An orchestration contract answers HOW the runtime traverses agents —
    neither what an agent can access (``CapabilityContract``) nor whether an
    operation is permitted (``GovernanceContract``).

    Characteristic properties:
    - Controls invocation count, sequencing, and result stitching across agents
    - Does NOT expose resource methods (no call_tool / send / emit pattern)
    - Does NOT enforce policy (no ``check()`` method)
    - Receives a fully wired ``MasRuntime`` and a resolved ``task`` dict
    - Multiple orchestration strategies are compositionally equivalent; any
      ``OrchestrationContract`` can be combined with any ``DesignPatternContract``

    Formal distinction:
      CapabilityContract  ↔  resource boundary  (POSIX syscall surface)
      GovernanceContract  ↔  policy boundary     (kernel security check)
      OrchestrationContract ↔  control topology  (scheduler / dispatch policy)
    """

    contract_id: ClassVar[Optional[str]] = None


# ---------------------------------------------------------------------------
# GovernanceContract
# ---------------------------------------------------------------------------

class GovernanceContract(ContractBase):
    """Base for contracts that enforce POLICY over capabilities.

    A governance contract answers "is this operation ALLOWED?".  It is applied
    by the runtime BEFORE capability contracts fire (and sometimes AFTER, for
    accounting).

    Characteristic properties:
    - check() raises ``PolicyViolation`` on denial; returns None on approval
    - Never "approves" explicitly — silence means permitted
    - Counters/state are MONOTONICALLY CONSUMED (budget, call counts)
    - Applied as cross-cutting concerns via hook composition

    Formal distinction from Petri net rate limits
    ─────────────────────────────────────────────
    Petri net place-bounded transitions enforce FLOW RATE (tokens are restored
    after each firing; the machine back-pressures or blocks temporarily).

    GovernanceContract enforces LIFETIME CEILINGS (counters decrement and never
    reset during a run; when exhausted the agent transitions permanently to
    S_BUDGET_EXHAUSTED or S_POLICY_DENIED).

      Petri net ↔ back-pressure / concurrency / throughput  (structural)
      GovernanceContract ↔ cost accounting / isolation / RBAC  (economic / policy)

    Adding / removing a governance contract is TOPOLOGY-NEUTRAL: the Mealy
    machine structure is unchanged; only the guard conditions on transitions
    are extended.

    Subclasses MUST implement ``check()``.
    """

    contract_id: ClassVar[Optional[str]] = None

    def check(self, operation: str, context: Dict) -> None:
        """Check whether ``operation`` with ``context`` is allowed.

        Args:
            operation: The operation being requested (e.g. "llm_call",
                       "tool_call:filesystem__read_file", "write:/etc/passwd").
            context:   Operation context dict (model, path, cost estimate…).

        Raises:
            PolicyViolation: if the operation is denied.

        Returns:
            None (silence = permitted).
        """
        pass  # default: permit all (override in concrete governance contracts)
