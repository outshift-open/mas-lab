#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""StateNode, TransNode, and LaneDef data model."""

from dataclasses import dataclass, field

from mas.lab.plots.multilevel_trajectory.constants import TYPE_COLOR

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
    parallel_group_id: str  = ""  # non-empty when this state is a fork/join boundary
    parallel_size:     int  = 0   # number of parallel branches at this fork/join
    cpr_data:  list = field(default_factory=list)  # CPR parts inherited from preceding ProcessingCall
    model:     str  = ""  # model name inherited from the LLM call record

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"s-{self.ts:.3f}"


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
    hover_in:   str  = ""
    hover_out:  str  = ""
    is_instant: bool = False  # True when call_type=="ProcessingCall" and duration ≈ 0
    cpr_data:  list = field(default_factory=list)  # structured CPR parts for rich JS rendering
    model:     str  = ""
    parallel_group_id: str = ""  # non-empty for transitions inside a parallel fork group
    parallel_rank:     int = 0   # 0-based branch index within the parallel group
    parallel_size:     int = 0   # total number of branches in the parallel group

    @property
    def color(self) -> str:
        return TYPE_COLOR.get(self.call_type, "#475569")


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
