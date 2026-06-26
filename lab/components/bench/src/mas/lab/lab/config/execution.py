#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class InfraEmulationSpec:
    """L1 infrastructure emulation: which backing resources are live vs controlled.

    In a controlled experiment the researcher varies one parameter while holding
    everything else stable.  When the independent variable lives at a layer above
    infrastructure (e.g. design pattern, governance policy, coordination topology),
    the layers below must be **deterministic**.  ``InfraEmulationSpec`` declares
    how each resource class is handled:

    * ``live``   — real remote call (network latency, non-determinism, cost)
    * ``mock``   — canned in-process response (zero latency, deterministic, free)
    * ``replay`` — play back a recorded response from the trace cache
    * ``stub``   — minimal implementation that satisfies the contract interface
    * ``ephemeral`` — memory that exists only for the duration of a single run

    The lab runner resolves these declarations into concrete plugin bindings
    before each scenario execution.  ``live`` is the default for production;
    ``mock`` / ``replay`` for CI and offline reproducibility.
    """

    llm: str = "live"
    """LLM model access: ``live`` | ``mock`` | ``replay``.

    ``mock``   → MockModelAccess (no network, canned responses).
    ``replay`` → responses served from the content-addressed trace cache.
    ``live``   → real LLM endpoint (via flavour).
    """

    tools: str = "live"
    """Tool backends: ``live`` | ``mock`` | ``stub``.

    ``mock`` → tools return fixed synthetic results (e.g. web_search always
    returns a canned snippet).  ``stub`` → tools satisfy the ToolContract
    interface but perform no real work.
    """

    memory: str = "live"
    """Semantic memory & workspace files: ``live`` | ``mock`` | ``snapshot`` | ``seeded`` | ``ephemeral``.

    ``ephemeral``  → in-memory store discarded after each run (InMemoryBackend).
    ``snapshot``   → memory restored from a checkpoint before each run
                     (deterministic starting knowledge base).
    ``seeded``     → memory initialised from a fixture then evolves freely.
    ``mock``       → memory search returns canned results regardless of
                     what was indexed (isolates reasoning from retrieval).
    ``live``       → real persistent storage (production default).
    """

    embeddings: str = "live"
    """Embedding service: ``live`` | ``mock`` | ``replay``.

    ``mock``   → returns a fixed-dimension zero/random vector (deterministic,
                 no network call).  Sufficient when the experiment does not
                 study retrieval quality.
    ``replay`` → embeddings served from a prior recorded trace.
    ``live``   → real embedding endpoint (via flavour).
    """

    state: str = "live"
    """External global state (KG, shared scratchpad, cross-agent blackboard):
    ``live`` | ``snapshot`` | ``seeded`` | ``ephemeral`` | ``mock``.

    Covers any mutable shared state that is *not* the semantic memory store
    (which has its own field).  Examples: knowledge graphs, shared context
    variables, external databases written to by tools.
    """

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InfraEmulationSpec":
        return cls(
            llm=data.get("llm", "live"),
            tools=data.get("tools", "live"),
            memory=data.get("memory", "live"),
            embeddings=data.get("embeddings", "live"),
            state=data.get("state", "live"),
        )


@dataclass
class RuntimeEmulationSpec:
    """L3 execution-engine emulation: how the runtime itself is controlled.

    Controls the runtime execution machinery independently of the resources
    it accesses (L1).  The key mechanism is the **content-addressed trace
    cache**: when ``cache`` is ``content-addressed``, a run that matches a
    previous (manifest, prompt, model, run_idx) fingerprint is skipped
    entirely — the cached trace is symlinked in place.  This is **execution
    replay**, not LLM replay: the entire MAS run (including all delegation,
    tool calls, and governance checks) is replayed from the event stream.

    ``transport`` controls agent-to-agent communication, which can be fully
    emulated in-process (``local``), routed over real gRPC (``grpc``), or
    simulated (``emulated``) with delay injection and message loss.
    """

    transport: str = "local"
    """Agent communication: ``local`` | ``grpc`` | ``emulated``."""

    cache: str = "content-addressed"
    """Trace cache policy: ``content-addressed`` | ``disabled`` | ``forced``.

    ``content-addressed`` — skip runs whose fingerprint already exists
    in the global cache (default, enables incremental experimentation).
    ``disabled`` — always execute live (useful for latency measurement).
    ``forced`` — fail if cache miss (fully offline replay).
    """

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeEmulationSpec":
        return cls(
            transport=data.get("transport", "local"),
            cache=data.get("cache", "content-addressed"),
        )


@dataclass
class InterceptSpec:
    """L3–L6 hook-level interception: MITM and fault injection.

    While overlays define *what* is intercepted (via ``capabilities.mitm``
    rules), this block declares the *experimental intent*: that hook-level
    interception is active and which hooks are targeted.  This makes the
    controlled-experiment design explicit in the experiment YAML, not buried
    in overlay files.

    When ``mitm`` is ``true``, the benchmark runner verifies that at least
    one scenario has a MITM overlay — a safety check that the interception
    is intentional, not accidental.
    """

    mitm: bool = False
    """Whether MITM hook interception is active in this experiment."""

    hooks: List[str] = field(default_factory=list)
    """Optional list of targeted hooks (e.g. ``["on_pre_llm_call"]``).

    Informational — used in experiment metadata and reports.
    """

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterceptSpec":
        return cls(
            mitm=data.get("mitm", False),
            hooks=data.get("hooks", []),
        )


@dataclass
class EmulationSpec:
    """Declares which layers of the execution stack are live vs controlled.

    The MAS-Lab architecture emulates the full execution engine (which in
    production might be Kubernetes, a gRPC mesh, real LLM endpoints, etc.).
    A controlled experiment requires **varying a single parameter** while
    keeping all other layers stable.  ``EmulationSpec`` makes this explicit:

    * **infra** (L1) — backing resources: LLM, tools, memory, embeddings, external state
    * **runtime** (L3) — execution engine: transport, trace cache
    * **intercept** (L3–L6) — hook-level interception: MITM, fault injection

    Layers not listed here (L2 structural, L5 trajectory, L6 governance,
    L7 interpretability) are controlled via the specification
    itself (overlays, patches) or via post-hoc analysis, not via emulation.

    Example — study the effect of a design-pattern change (L5 independent
    variable) while holding infrastructure deterministic::

        emulation:
          infra:
            llm: replay        # L1: deterministic LLM responses from cache
            tools: mock        # L1: deterministic tool outputs
            memory: snapshot   # L1: memory restored from checkpoint
            embeddings: mock   # L1: fixed embedding vectors
          runtime:
            cache: content-addressed
          intercept:
            mitm: false        # no hook interception in this experiment
    """

    infra: InfraEmulationSpec = field(default_factory=InfraEmulationSpec)
    """L1 infrastructure emulation."""

    runtime: RuntimeEmulationSpec = field(default_factory=RuntimeEmulationSpec)
    """L3 execution-engine emulation."""

    intercept: InterceptSpec = field(default_factory=InterceptSpec)
    """L3–L6 hook-level interception."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmulationSpec":
        return cls(
            infra=InfraEmulationSpec.from_dict(data.get("infra", {})),
            runtime=RuntimeEmulationSpec.from_dict(data.get("runtime", {})),
            intercept=InterceptSpec.from_dict(data.get("intercept", {})),
        )


# ---------------------------------------------------------------------------
# ExecutionSpec — batch execution parameters (used by MASExperimentConfig)
# ---------------------------------------------------------------------------

@dataclass
class MASExecutionSpec:
    """Batch execution parameters for MASExperimentConfig.

    Parallel to the ``execution:`` block in single-agent ``ExperimentConfig``.
    """

    n_runs: int = 3
    """Number of times each scenario × flavour combination is executed."""

    parallel_scenarios: int = 4
    """Maximum number of concurrent MAS runs."""

    timeout: int = 300
    """Per-run timeout in seconds."""

    pause_between_runs: float = 1.0
    """Pause in seconds between runs to let resources settle."""

    strategy: str = "coverage"
    """Execution ordering: coverage (breadth-first) or depth."""

    runner: str = "mas"
    """Application runner registry id."""

    design: Optional[Dict[str, Any]] = None
    """Experiment design mode (cartesian, coupled, one_factor) and guards."""

    replay: Optional["ReplaySpec"] = None
    """Multi-turn replay configuration.  When set, dataset items with a
    ``turns`` list are executed as multi-turn conversations."""

    emulation: EmulationSpec = field(default_factory=EmulationSpec)
    """Layered emulation configuration.

    Declares which layers of the execution stack are live vs controlled
    (mocked / replayed / intercepted).  This is the mechanism that enables
    controlled experiments: vary one parameter, keep the rest stable.
    """

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MASExecutionSpec":
        replay_data = data.get("replay")
        emulation_data = data.get("emulation", {})
        return cls(
            n_runs=data.get("n_runs", 3),
            parallel_scenarios=data.get("parallel_scenarios", 4),
            timeout=data.get("timeout", 300),
            pause_between_runs=data.get("pause_between_runs", 1.0),
            strategy=data.get("strategy", "coverage"),
            runner=data.get("runner", "mas"),
            design=data.get("design"),
            replay=ReplaySpec.from_dict(replay_data) if replay_data else None,
            emulation=EmulationSpec.from_dict(emulation_data),
        )


# ---------------------------------------------------------------------------
# ReplaySpec — multi-turn conversation replay configuration
# ---------------------------------------------------------------------------

@dataclass
class ReplaySpec:
    """Controls how multi-turn dataset items are replayed.

    When a dataset item contains a ``turns`` list, the benchmark runner
    feeds each turn sequentially to the same MAS runtime instance (preserving
    session context).  The ``replay`` block in the experiment YAML controls
    additional replay behaviour.

    Modes
    -----
    ``scripted``  (default)
        Every turn in ``item.turns`` is replayed exactly as written.
        HITL responses are injected from the dataset.

    ``cache-and-diverge``
        Uses the trace-cache from a previous run.  Replays cached turns until
        data diverges, then continues live.

    HITL source
    -----------
    ``dataset``
        HITL responses are read from the ``turns`` list.

    ``recording``
        HITL responses are loaded from a recording file (``mas-runtime run-agent --record``).
    """

    mode: str = "scripted"
    """Replay mode: ``scripted`` or ``cache-and-diverge``."""

    hitl_source: str = "dataset"
    """Source for HITL responses: ``dataset`` or ``recording``."""

    recording_path: Optional[str] = None
    """Path to a recording JSON (when hitl_source='recording')."""

    diverge_from_cache: bool = True
    """In cache-and-diverge mode, continue live after first divergence."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplaySpec":
        return cls(
            mode=data.get("mode", "scripted"),
            hitl_source=data.get("hitl_source", "dataset"),
            recording_path=data.get("recording_path"),
            diverge_from_cache=data.get("diverge_from_cache", True),
        )

