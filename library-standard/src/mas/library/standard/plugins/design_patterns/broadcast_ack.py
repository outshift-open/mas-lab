#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Broadcast-and-ack deterministic design pattern — converging message bus.

Any agent that has something to say sends a message that is delivered to
all other participants in the next wave.  This repeats until every agent
in a wave responds with a bare ack (nothing new to add), a SIEP-style
majority position agreement is detected, or the safety cap is reached.

Protocol:
  Wave 1    — original message fans out to all participants simultaneously.
  Wave N+1  — every non-ack reply from wave N is delivered to all other
               participants simultaneously (each agent receives only the
               messages sent by others, not their own).
  Terminate — when no participant has a new message (all ack in the same
               wave), when a majority of tracked confidence positions
               converge within the agreement threshold, or when max_rounds
               is reached.

CIP contingency handling (CIP = Contingency Interaction Protocol):
  When two agents exchange non-ack replies in D_MAX_CONTINGENCY consecutive
  waves without either backing down, they are declared "in contingency".
  A focused bilateral clarification wave is dispatched between just those
  two agents, asking each to directly address the other's specific concern.
  The outcome is one of:
    resolved  — at least one agent updates or accepts the other's position.
    exhausted — both agents still disagree; the pair is marked unresolved
                and the main broadcast continues without them.
  At most one contingency pair is handled per wave; if multiple pairs are
  in contingency the oldest is resolved first.

SIEP metrics (appended to final output when confidence data is available):
  MPC — Mean Posterior Confidence across all agents with tracked positions.
  GAR — Genuine Agreement Ratio: fraction of agents whose final confidence
        shifted more than 5 pp from their initial position (wave-1 prior).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.parallel_tools import schedule_parallel_tools_egress
from mas.runtime.kernel.state import QProduct, RunEvent, RunLedger
from mas.runtime.schema.egress import EgressSymbol
from mas.runtime.schema.ingress import ToolCallSpec

from .base import _DeterministicBase, _TurnState
from .utils import dispatch_parallel

_MAX_ROUNDS = 6        # safety cap — override via spec.design_pattern.params.max_rounds
_AGREE_THRESHOLD = 0.15  # max spread from median for majority-agreement check (SIEP P3)
_GAR_DELTA = 0.05      # minimum posterior shift to count as genuine movement (SIEP θ_belief)

# Injected at the end of every task the framework sends so agents need no
# protocol knowledge in their own YAML — the rule arrives at call time.
_ACK_RULE = (
    "PROTOCOL: When you have nothing new to contribute, reply with the single "
    "word ACK on its own line — no headers, no punctuation, no explanation."
)

# CIP constants — d_max_contingency can be overridden via design_pattern.params
_D_MAX_CONTINGENCY = 2   # consecutive waves both agents have non-ack → contingency
_CIP_MAX_DEPTH = 2       # max bilateral clarification rounds before exhaustion

# Confidence extraction — labeled patterns only.
# Bare percentages are intentionally excluded: domain content routinely contains
# percentages that are not confidence values ("exceeded by 71%", "100% capacity"),
# and misidentifying them as confidence scores causes false SIEP convergence.
_CONFIDENCE_RE = re.compile(
    r'(?:confidence|certainty|posterior|probability)[:\s~]+(\d{1,3}(?:\.\d+)?)\s*%?',
    re.IGNORECASE,
)


def _extract_confidence(text: str) -> float | None:
    """Return a 0–1 confidence float from a labeled pattern, or None if not found.

    Recognises labeled patterns only:
      "confidence: 0.70"  "confidence ~70%"  "posterior: 0.65"  "certainty: 80%"
    Bare percentages (e.g. "71%") are intentionally ignored — domain content
    routinely uses them for non-confidence quantities.
    Values > 1.5 are assumed to be percentages and divided by 100.
    """
    m = _CONFIDENCE_RE.search(text)
    if m is None:
        return None
    val = float(m.group(1))
    return val / 100.0 if val > 1.5 else val


def _is_ack(text: str) -> bool:
    """Return True when the response is a bare acknowledgement, not a reply.

    Handles two forms agents commonly produce:
      - First word is ACK (possibly wrapped in markdown: **ACK**, *ACK*).
      - Message ends with a standalone ACK on its own line, preceded by
        explanation text, e.g. "I have nothing new to add.\n\nACK".
        The last-line check requires the line to contain only the single word
        ACK to avoid mis-classifying lines like "...safety comes first. ACK"
        where ACK is inline within a longer sentence.
    """
    stripped = text.strip()
    if not stripped:
        return True

    def _word_is_ack(word: str) -> bool:
        cleaned = re.sub(r'^[*_`]+|[*_`.,!?:]+$', '', word)
        return cleaned.upper() == "ACK"

    # Check first word.
    if _word_is_ack(stripped.split()[0]):
        return True

    # Check last non-empty line: must be a single word that is ACK.
    last_line = stripped.splitlines()[-1].strip()
    words = last_line.split()
    return len(words) == 1 and _word_is_ack(words[0])


@dataclass
class _ContingencyPair:
    """State for an active CIP repair episode between two agents."""
    agent_a: str
    agent_b: str
    # Consecutive waves both were non-ack (used to detect onset)
    consecutive_waves: int = 0
    # How many bilateral clarification rounds have been dispatched
    cip_depth: int = 0
    # True once the pair enters the active clarification phase
    active: bool = False
    # Final outcome once the pair's repair episode closes
    outcome: str | None = None   # None | "resolved" | "exhausted"
    # Most recent texts from each agent (used to build clarification prompt)
    last_text_a: str = ""
    last_text_b: str = ""

    @property
    def key(self) -> frozenset[str]:
        return frozenset([self.agent_a, self.agent_b])

    def agents(self) -> tuple[str, str]:
        return self.agent_a, self.agent_b


@dataclass
class _BroadcastAckState(_TurnState):
    # correlation_id → agent_id, rebuilt at every dispatch
    cid_to_agent: dict[int, str] = field(default_factory=dict)
    # Chronological log of (wave_num, agent_id, text) for every non-ack reply
    reply_log: list[tuple[int, str, str]] = field(default_factory=list)
    max_rounds: int = _MAX_ROUNDS
    # CIP: how many consecutive waves of mutual non-ack trigger contingency
    d_max_contingency: int = _D_MAX_CONTINGENCY
    # SIEP-style position tracking: first non-ack confidence per agent (wave 1)
    initial_priors: dict[str, float] = field(default_factory=dict)
    # Most-recent non-ack confidence per agent (updated each wave)
    final_positions: dict[str, float] = field(default_factory=dict)
    # CIP: per-pair contingency tracking keyed by frozenset({a, b})
    cip_pairs: dict[frozenset, _ContingencyPair] = field(default_factory=dict)
    # CIP: pair currently in active bilateral clarification (only one at a time)
    active_cip_pair: frozenset | None = None
    # CIP: log of resolved/exhausted pair summaries for final output
    cip_log: list[str] = field(default_factory=list)
    # Set to False via design_pattern.params.l9=false to run without CIP/SIEP
    l9_enabled: bool = True


class BroadcastAckPlugin(_DeterministicBase):
    """Converging broadcast bus with CIP contingency repair.

    Wave 1: all peers receive the original message.
    Wave N+1: every non-ack reply from wave N is delivered to all other
              peers simultaneously.  Repeats until convergence or max_rounds.
    CIP: pairs that persistently disagree trigger a focused bilateral
         clarification exchange before the main broadcast resumes.
    """

    plugin_id = "broadcast_ack@v1"
    mode = "broadcast_ack"

    def _make_state(self) -> _BroadcastAckState:
        return _BroadcastAckState()

    def _st(self) -> _BroadcastAckState:
        return self._turn_state  # type: ignore[return-value]

    def _capture_cid_map(self, q: QProduct) -> None:
        st = self._st()
        for cid, (tool_name, _) in q.pending_tools_by_cid.items():
            st.cid_to_agent[cid] = tool_name[len("delegate_to_"):]

    def _current_wave_results(self, events: list[RunEvent]) -> dict[str, str]:
        """Return agent_id → text for the current wave (keyed by cid_to_agent)."""
        st = self._st()
        out: dict[str, str] = {}
        for ev in events:
            if ev.response_kind != "TOOL_RESULT":
                continue
            agent_id = st.cid_to_agent.get(ev.correlation_id)
            if agent_id and agent_id not in out:
                out[agent_id] = ev.text or ""
        return out

    def _dispatch_wave(
        self,
        q: QProduct,
        run: RunLedger,
        config: KernelConfig,
        inbox: dict[str, list[tuple[str, str]]],  # agent_id → [(sender_id, text)]
    ) -> list[EgressSymbol]:
        """Fan out per-agent inboxes in parallel; capture the new cid map."""
        st = self._st()
        st.cid_to_agent.clear()
        specs: list[ToolCallSpec] = []
        for recipient, messages in inbox.items():
            lines = [f"- {sid}: {msg}" for sid, msg in messages]
            task = (
                f"Original message: {st.original_task}\n\n"
                f"New messages from other agents:\n" + "\n".join(lines) + "\n\n"
                + _ACK_RULE
            )
            specs.append(ToolCallSpec(
                tool_name=self._delegate_tool_name(recipient),
                tool_arguments={"task": task},
            ))
        egress = schedule_parallel_tools_egress(q, run, config, specs)
        self._capture_cid_map(q)
        return egress

    def _track_positions(self, wave_results: dict[str, str]) -> None:
        """Update SIEP confidence tracking from non-ack wave replies."""
        st = self._st()
        for agent_id, text in wave_results.items():
            if not text.strip() or _is_ack(text.strip()):
                continue
            conf = _extract_confidence(text)
            if conf is None:
                continue
            st.final_positions[agent_id] = conf
            st.initial_priors.setdefault(agent_id, conf)

    def _majority_agreed(self) -> bool:
        """True when > n/2 agents' final positions are within _AGREE_THRESHOLD of the median.

        Uses the median (not the mean) as the cluster reference so that a single
        outlier does not drag the anchor away from the majority cluster — e.g.
        two agents at 70% and one at 10% correctly identify 70% as the cluster
        centre. Mirrors SIEP's spread-threshold convergence path.
        Requires at least two tracked positions to avoid spurious early exits.
        """
        st = self._st()
        positions = sorted(st.final_positions.values())
        if len(positions) < len(st.participants):
            return False
        mid = len(positions) // 2
        median = positions[mid] if len(positions) % 2 else (positions[mid - 1] + positions[mid]) / 2
        close = sum(1 for p in positions if abs(p - median) <= _AGREE_THRESHOLD)
        return close * 2 > len(st.participants)

    def _siep_metrics(self) -> str:
        """Return a MPC / GAR summary line, or empty string if no data."""
        st = self._st()
        if not st.final_positions:
            return ""
        mpc = sum(st.final_positions.values()) / len(st.final_positions)
        if st.initial_priors:
            shifted = sum(
                1 for aid, final in st.final_positions.items()
                if abs(final - st.initial_priors.get(aid, final)) > _GAR_DELTA
            )
            gar = shifted / len(st.participants)
        else:
            gar = 0.0
        return f"MPC {mpc:.0%}  ·  GAR {gar:.0%}"

    # ------------------------------------------------------------------
    # CIP contingency detection and bilateral repair
    # ------------------------------------------------------------------

    def _update_cip_tracking(self, non_ack_agents: set[str]) -> None:
        """Update consecutive-wave counters for all agent pairs."""
        st = self._st()
        for a, b in combinations(sorted(st.participants), 2):
            key = frozenset([a, b])
            pair = st.cip_pairs.get(key)
            if pair is None:
                pair = _ContingencyPair(agent_a=a, agent_b=b)
                st.cip_pairs[key] = pair
            if pair.outcome is not None or pair.active:
                continue
            if a in non_ack_agents and b in non_ack_agents:
                pair.consecutive_waves += 1
            else:
                pair.consecutive_waves = 0

    def _find_contingency_pair(self) -> _ContingencyPair | None:
        """Return the first pair that has reached the contingency threshold."""
        st = self._st()
        for pair in st.cip_pairs.values():
            if pair.outcome is None and not pair.active and pair.consecutive_waves >= st.d_max_contingency:
                return pair
        return None

    def _dispatch_cip_wave(
        self,
        q: QProduct,
        run: RunLedger,
        config: KernelConfig,
        pair: _ContingencyPair,
        wave_results: dict[str, str],
    ) -> list[EgressSymbol]:
        """Dispatch a focused bilateral clarification wave for a contingency pair."""
        st = self._st()
        a, b = pair.agents()

        # Update last known texts from this wave (or keep previous if not present).
        if a in wave_results and not _is_ack(wave_results[a]):
            pair.last_text_a = wave_results[a].strip()
        if b in wave_results and not _is_ack(wave_results[b]):
            pair.last_text_b = wave_results[b].strip()

        pair.active = True
        pair.cip_depth += 1
        st.active_cip_pair = pair.key

        st.cid_to_agent.clear()
        specs = [
            ToolCallSpec(
                tool_name=self._delegate_tool_name(a),
                tool_arguments={"task": (
                    f"Original message: {st.original_task}\n\n"
                    f"You and {b} have a persistent disagreement. "
                    f"{b} says: \"{pair.last_text_b}\"\n\n"
                    f"Please directly address {b}'s specific concern. "
                    f"If you can accept or update your position, do so. "
                    f"Otherwise state clearly what evidence would change your view.\n\n"
                    + _ACK_RULE
                )},
            ),
            ToolCallSpec(
                tool_name=self._delegate_tool_name(b),
                tool_arguments={"task": (
                    f"Original message: {st.original_task}\n\n"
                    f"You and {a} have a persistent disagreement. "
                    f"{a} says: \"{pair.last_text_a}\"\n\n"
                    f"Please directly address {a}'s specific concern. "
                    f"If you can accept or update your position, do so. "
                    f"Otherwise state clearly what evidence would change your view.\n\n"
                    + _ACK_RULE
                )},
            ),
        ]
        egress = schedule_parallel_tools_egress(q, run, config, specs)
        self._capture_cid_map(q)
        return egress

    def _resolve_cip_wave(self, wave_results: dict[str, str]) -> None:
        """Process results of a bilateral CIP clarification wave."""
        st = self._st()
        if st.active_cip_pair is None:
            return
        pair = st.cip_pairs.get(st.active_cip_pair)
        if pair is None:
            return

        a, b = pair.agents()
        text_a = wave_results.get(a, "").strip()
        text_b = wave_results.get(b, "").strip()

        # At least one agent ACKing = resolved.
        if _is_ack(text_a) or _is_ack(text_b):
            pair.outcome = "resolved"
            who_resolved = a if _is_ack(text_a) else b
            st.cip_log.append(
                f"[CIP resolved] {a} ↔ {b}: {who_resolved} accepted the other's position "
                f"after {pair.cip_depth} clarification round(s)."
            )
        elif pair.cip_depth >= _CIP_MAX_DEPTH:
            pair.outcome = "exhausted"
            st.cip_log.append(
                f"[CIP exhausted] {a} ↔ {b}: persistent disagreement after "
                f"{pair.cip_depth} clarification round(s) — marked unresolved."
            )
        # else: not yet resolved and under depth limit — will dispatch another round next wave

        if pair.outcome is not None:
            pair.active = False
            st.active_cip_pair = None
            # Record the non-ack texts in the main reply_log so they appear in output.
            for agent_id, text in [(a, text_a), (b, text_b)]:
                if text and not _is_ack(text):
                    st.reply_log.append((st.round_num, agent_id, text))

    def _build_final(self, q: QProduct, converged: bool) -> list[EgressSymbol]:
        st = self._st()
        if not st.reply_log:
            return self._finish(
                q,
                f"Broadcast acknowledged by all participants "
                f"(no substantive replies after {st.round_num} wave(s)).",
            )

        # Group contributions per agent, in wave order.
        by_agent: dict[str, list[tuple[int, str]]] = {}
        for wave, agent_id, text in st.reply_log:
            by_agent.setdefault(agent_id, []).append((wave, text))

        parts: list[str] = []
        for agent_id in st.participants:
            contribs = by_agent.get(agent_id)
            if not contribs:
                continue
            if len(contribs) == 1:
                parts.append(f"=== {agent_id} ===\n{contribs[0][1]}")
            else:
                lines = [f"[Wave {w}] {txt}" for w, txt in contribs]
                parts.append(f"=== {agent_id} ===\n" + "\n".join(lines))

        silent = [p for p in st.participants if p not in by_agent]
        if silent:
            parts.append(f"[{len(silent)} peer(s) acknowledged without reply: {', '.join(silent)}]")

        if st.cip_log:
            parts.append("\n".join(st.cip_log))

        label = "converged" if converged else f"stopped after {st.round_num} wave(s) (max reached)"
        metrics = self._siep_metrics() if st.l9_enabled else ""
        footer = f"[Broadcast {label}]" + (f"  [{metrics}]" if metrics else "")
        parts.append(footer)
        return self._finish(q, "\n\n".join(parts))

    def evaluate_next(self, q: QProduct, run: RunLedger, config: KernelConfig) -> list[EgressSymbol]:
        st = self._st()
        if not st.participants:
            return self._no_participants(q)

        # Read tunable params from agent spec if provided.
        spec = getattr(config, "agent_spec", None) or {}
        dp_params = ((spec.get("design_pattern") or {}).get("params") or {}) if isinstance(spec, dict) else {}
        st.max_rounds = int(dp_params.get("max_rounds", st.max_rounds))
        st.d_max_contingency = int(dp_params.get("d_max_contingency", st.d_max_contingency))
        if "l9" in dp_params:
            st.l9_enabled = bool(dp_params["l9"])

        # Wave 1: fan-out the original message to all participants.
        if st.next_idx == 0:
            st.next_idx = 1
            task = f"{st.original_task}\n\n{_ACK_RULE}"
            egress = dispatch_parallel(self, q, run, config, task, st.participants)
            self._capture_cid_map(q)
            return egress

        # Collect this wave's results.
        wave_results = self._current_wave_results(run.events)

        # If we are in an active CIP clarification, resolve it first.
        if st.active_cip_pair is not None:
            self._resolve_cip_wave(wave_results)
            # If the pair resolved/exhausted, resume the main broadcast next wave.
            # If still active (under depth limit), dispatch another clarification round.
            if st.active_cip_pair is not None:
                # Still active — dispatch another CIP round.
                pair = st.cip_pairs[st.active_cip_pair]
                return self._dispatch_cip_wave(q, run, config, pair, wave_results)
            # Pair is closed — fall through to continue main broadcast.
            # The main wave results from this pass were the CIP bilateral results,
            # so we don't process them as normal broadcast replies.
            st.round_num += 1
            # Re-dispatch the last known non-ack agents (excluding now-resolved pair
            # if one of them acked) to continue the broadcast.
            # For simplicity: re-examine the reply_log to find what messages are
            # pending. Agents that are resolved/exhausted can still participate
            # in the main broadcast with their latest positions.
            # Build inbox from the most-recent reply_log entries since last broadcast wave.
            last_wave_msgs: dict[str, str] = {}
            for w, aid, txt in reversed(st.reply_log):
                if aid not in last_wave_msgs:
                    last_wave_msgs[aid] = txt
                if len(last_wave_msgs) == len(st.participants):
                    break
            if not last_wave_msgs:
                return self._build_final(q, converged=True)
            inbox: dict[str, list[tuple[str, str]]] = {}
            for recipient in st.participants:
                messages = [(sid, msg) for sid, msg in last_wave_msgs.items() if sid != recipient]
                if messages:
                    inbox[recipient] = messages
            if not inbox:
                return self._build_final(q, converged=True)
            return self._dispatch_wave(q, run, config, inbox)

        # Normal broadcast wave: accumulate non-ack replies.
        for agent_id, text in wave_results.items():
            stripped = text.strip()
            if stripped and not _is_ack(stripped):
                st.reply_log.append((st.round_num, agent_id, stripped))
        if st.l9_enabled:
            self._track_positions(wave_results)

        # Find agents that sent a new message this wave.
        new_messages: dict[str, str] = {
            aid: text.strip()
            for aid, text in wave_results.items()
            if text.strip() and not _is_ack(text.strip())
        }

        # Convergence: no one had anything new to say.
        if not new_messages:
            return self._build_final(q, converged=True)

        # SIEP majority-agreement check: stop early when positions have converged.
        if st.l9_enabled and self._majority_agreed():
            return self._build_final(q, converged=True)

        # Safety cap.
        if st.round_num >= st.max_rounds:
            return self._build_final(q, converged=False)

        # CIP: update pair tracking and check for contingency.
        if st.l9_enabled:
            self._update_cip_tracking(set(new_messages.keys()))
            cip_pair = self._find_contingency_pair()
            if cip_pair is not None:
                st.round_num += 1
                return self._dispatch_cip_wave(q, run, config, cip_pair, new_messages)

        # Build inboxes: each participant receives every other participant's new message.
        inbox = {}
        for recipient in st.participants:
            messages = [(sid, msg) for sid, msg in new_messages.items() if sid != recipient]
            if messages:
                inbox[recipient] = messages

        if not inbox:
            return self._build_final(q, converged=True)

        st.round_num += 1
        return self._dispatch_wave(q, run, config, inbox)
