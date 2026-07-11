#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""StateNode, TransNode, and LaneDef data model."""

from dataclasses import dataclass, field

from mas.lab.plots.multilevel_trajectory.constants import TYPE_COLOR
from mas.lab.plots.multilevel_trajectory.governance import governance_color

@dataclass
class StateNode:
    """A shared state node — one instance per distinct timestamp.

    States are shared across lanes: two lanes that both have an execution
    record boundary at the same timestamp reference the *same* ``StateNode``
    object.  The renderer draws a vertical dashed connector between lanes
    that share a state.

    ``hover`` is the global fallback content (highest-priority level wins).
    ``hover_by_lane`` stores per-lane overrides so each lane shows its own
    content — e.g. the Agent lane shows agent output while the Calls lane
    shows call input at the same shared state boundary.

    ``is_user_entry`` / ``is_user_exit`` mark the session boundary states.
    The renderer may draw them as stickman actor shapes.
    """
    ts:            float
    hover:         str  = ""
    hover_by_lane: dict = field(default_factory=dict)  # lane_id → hover text
    node_id:       str  = ""
    is_user_entry: bool = False
    is_user_exit:  bool = False
    label_override: str = ""  # e.g. "S2a" for thinking sub-states; overrides S{n} when non-empty
    is_lane_restart: bool = False  # thinking lane: breaks lifeline at agent boundary
    is_connector_only: bool = False  # injected for sharedBuckets — rendered as invisible dot (no box)
    is_interrupted: bool = False  # agent had no execution_end — trace was cut while running
    is_error:       bool = False  # execution_end.status was non-success
    is_fork:        bool = False  # parallel fork point (two agents branch here)
    is_join:        bool = False  # parallel join point (two branches merge here)
    fork_of:        str | None = None  # node_id of the fork point this state joins
    join_of:        list[str] = field(default_factory=list)  # node_ids of every branch's end state that merges here
    parallel_group_id: str  = ""  # non-empty when this state is a fork/join boundary
    parallel_size:     int  = 0   # number of parallel branches at this fork/join
    # "agent" — a genuine cross-agent delegation fork (the delegating agent
    # dispatched 2+ OTHER agents concurrently; branches run on the Agents
    # lane). "tool" — a single agent's own N tool calls dispatched
    # concurrently (branches never leave that one agent's own Calls-lane
    # row). Both are real, native parallel_group facts, but conflating them
    # under identical "fork"/"join" wording+styling was reported as
    # impossible to understand (a same-agent tool fan-out visually reads
    # exactly like a hand-off to other agents) — the renderer uses this to
    # give each kind its own icon/colour/wording. Empty string only for
    # states that predate this field (should not occur for any is_fork/
    # is_join state built by the current dag.py).
    fork_kind:         str  = ""
    # Renderer-facing navigation for fork/join hyperlinks (see dag.py's
    # `_build_dag` agent-lane loop). fork_branch_ts is set ONLY on the fork
    # state itself: the ts of each branch's own entry point, in rank order
    # (rank 0's entry IS this same state, so its own ts is included first).
    # join_fork_ts is set ONLY on the join state: the ts of the matching fork
    # state for the same parallel_group_id, so the renderer can draw a
    # "back to fork" link symmetrical to the fork's own "go to branch N"
    # links. join_ts is the mirror image, set ONLY on the fork state: the ts
    # of its own matching join/merge state — so fork and join are fully
    # cross-linked in both directions (fork.join_ts <-> join.join_fork_ts),
    # not just join -> fork. Both are plain native facts (already known at
    # DAG-build time), never client-side heuristics.
    fork_branch_ts: list[float] = field(default_factory=list)
    join_fork_ts:   float | None = None
    join_ts:        float | None = None
    # DFS virtual-position axis (see tree.py's _assign_dfs_positions): dfs_pos
    # is a monotonic position in DFS visitation order, NOT real time — it is
    # what the renderer's x-axis is built from. branch_id is the real call_id
    # of the branch's own child (never a synthetic counter). is_branch_reset
    # marks the specific state where the renderer draws a full-height dashed
    # separator, because layout here jumped from one DFS branch to the next
    # sibling rather than continuing forward in real time.
    dfs_pos:         float = 0.0
    branch_id:       str   = ""
    is_branch_reset: bool  = False
    # Branch begin/end markers: distinct from the fork/join boundary itself
    # (is_fork/is_join above mark only the SPLIT/MERGE point shared by every
    # branch) — these mark each INDIVIDUAL branch's own entry/exit point
    # inside a parallel_group_id, so a 5-way fork renders 1 fork node PLUS 5
    # branch-begin + 5 branch-end markers (one pair per branch), even though
    # rank 0's own begin coincides with the fork state itself (both flags can
    # be true on the same StateNode; the renderer layers both visuals there).
    # See dag.py's fork/join loops for where these are stamped.
    is_branch_begin: bool = False
    is_branch_end:   bool = False
    # This one branch's OWN other endpoint — set bidirectionally on both
    # the branch's begin state (-> its own end's ts) and its end state
    # (-> its own begin's ts), mirroring the fork<->join join_ts/
    # join_fork_ts cross-link pattern above. Needed because branches in the
    # same parallel_group_id are NOT guaranteed to finish in dispatch order
    # (genuinely concurrent branches can legitimately interleave/finish out
    # of rank order), so a begin cannot be safely re-paired with an end by
    # ts-proximity alone — this is a plain native fact recorded at DAG-build
    # time (same rank/call_id), never a client-side heuristic. None when
    # the partner state isn't known (should not occur for any is_branch_begin/
    # is_branch_end state built by the current dag.py).
    branch_partner_ts: float | None = None
    cpr_data:  list = field(default_factory=list)  # CPR parts inherited from preceding ProcessingCall
    cpr_mode:  str  = ""  # "diff" or "snapshot" (renderer hint)
    context_operation: str = ""  # APPEND/PREPEND/... when known from trace
    wait_link_id: str = ""  # non-empty for WAIT/RESUME paired states
    wait_role: str = ""  # "WAIT" or "RESUME"
    wait_note: str = ""  # short explanatory text for pending/resume state
    wait_meta: dict = field(default_factory=dict)  # structured wait/resume metadata for renderer cards
    suppress_cpr: bool = False  # True => never auto-fill CPR on this state
    assembly_note: str = ""  # join state only: native "parallel aggregation" summary (e.g. "aggregate 2 parallel tool results")
    model:     str  = ""  # model name inherited from the LLM call record
    # Owning agent for this state's own facts (mirrors TransNode.agent_id).
    # Used by the renderer's per-agent CPR accumulation to reset facts when
    # a state itself belongs to a different agent than the previous state,
    # even when the two aren't bridged by a TransNode whose own agentId has
    # already changed (e.g. a delegate's very first state, shared by ts with
    # its delegator's own wait boundary).
    agent_id:  str  = ""
    # Governance decisions that stopped a call before it ever reached the
    # engine (BLOCK/TERMINATE/SKIP/BLACKLIST) have no execution record to
    # attach to — they are marked on the nearest state boundary instead, as a
    # connector-only marker (see dag.py's blocked-action injection).
    governance: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"s-{self.ts:.3f}"

    @property
    def governance_color(self) -> str:
        """Severity color for the worst decision in ``governance`` (computed
        here, not re-derived client-side, so the frontend never needs its
        own copy of the severity ranking)."""
        return governance_color(self.governance)


@dataclass
class TransNode:
    """A transition node — one per execution record, belongs to exactly one lane."""
    node_id:   str
    call_type: str
    label:     str
    start_ts:  float
    end_ts:    float
    level:     str
    agent_id:  str
    seq:       int
    call_id:   str  = ""  # runtime call_id backing this visual transition when available
    hover_in:   str  = ""
    hover_out:  str  = ""
    missing_telemetry: list[str] = field(default_factory=list)  # fields absent in telemetry for this node
    is_instant: bool = False  # True when call_type=="ProcessingCall" and duration ≈ 0
    # True for a transition slice manufactured purely to bridge a mirrored
    # WAIT/RESUME boundary onto another lane (see dag.py's
    # _insert_agent_boundary) — it carries no independent activity of its
    # own, so the renderer draws no bar/label for it (state alternation is
    # still satisfied, this only suppresses the visual).
    connector_only: bool = False
    cpr_data:  list = field(default_factory=list)  # structured CPR parts for rich JS rendering
    cpr_mode:  str  = ""  # "diff" or "snapshot" (renderer hint)
    context_operation: str = ""  # APPEND/PREPEND/... when known from trace
    processing_type: str = ""  # ProcessingCall subtype (e.g., wait_state, parallel_group)
    processing_name: str = ""  # ProcessingCall operation label from telemetry
    model:     str  = ""
    parallel_group_id: str = ""  # non-empty for transitions inside a parallel fork group
    parallel_rank:     int = 0   # 0-based branch index within the parallel group
    parallel_size:     int = 0   # total number of branches in the parallel group
    # DFS virtual-position axis — see StateNode's matching fields for the
    # full explanation. dfs_pos_start/end are this transition's own span in
    # that same virtual coordinate space (real start_ts/end_ts are untouched
    # and still drive hover/duration text).
    dfs_pos_start: float = 0.0
    dfs_pos_end:   float = 0.0
    branch_id:     str   = ""
    # Governance decisions that gated this call: [{hook, checkpoint, decision,
    # reason, policyName}, ...] — usually one egress + one ingress entry.
    governance: list = field(default_factory=list)
    # Split governance view for boundary indicators (enter/exit badges).
    governance_egress: list = field(default_factory=list)
    governance_ingress: list = field(default_factory=list)
    # Non-empty when this call is one attempt in a governance-triggered retry
    # chain (see governance.py's _collect_retry_chains).
    retry_group_id: str = ""
    retry_attempt:  int = 0

    @property
    def color(self) -> str:
        return TYPE_COLOR.get(self.call_type, "#475569")

    @property
    def governance_color(self) -> str:
        """Severity color for the worst decision in ``governance`` (computed
        here, not re-derived client-side, so the frontend never needs its
        own copy of the severity ranking)."""
        return governance_color(self.governance)

    @property
    def governance_egress_color(self) -> str:
        """Severity color for egress-side governance decisions."""
        return governance_color(self.governance_egress)

    @property
    def governance_ingress_color(self) -> str:
        """Severity color for ingress-side governance decisions."""
        return governance_color(self.governance_ingress)


@dataclass
class LaneDef:
    """One horizontal swim lane.

    ``sequence`` is a strict alternating list  ``[StateNode, TransNode,
    StateNode, TransNode, …, StateNode]``.  Two consecutive ``StateNode``
    items never appear without a ``TransNode`` between them.
    """
    lane_id:  str
    level:    str
    label:    str
    sequence: list = field(default_factory=list)
    connector_only_ts: set = field(default_factory=set)
    parallel_spans: list = field(default_factory=list)  # [{startTs, endTs, size}, …]
