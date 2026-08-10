#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Broadcast-and-ack deterministic design pattern.

The entry agent fans out the message to every participant in parallel.
Each participant can either send a substantive reply or return a bare
acknowledgement.  An ack is any response that is empty or whose first
word is "ACK" (case-insensitive).  The broadcaster collects all acks
(confirming delivery) and aggregates only the substantive replies into
the final response.
"""

from __future__ import annotations

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.state import QProduct, RunLedger
from mas.runtime.schema.egress import EgressSymbol

from .base import _DeterministicBase
from .utils import dispatch_parallel


def _is_ack(text: str) -> bool:
    """Return True when the response is a bare acknowledgement, not a reply."""
    stripped = text.strip()
    if not stripped:
        return True
    first_word = stripped.split()[0].rstrip(":,.!?").upper()
    return first_word == "ACK"


class BroadcastAckPlugin(_DeterministicBase):
    """Broadcast + ack — all peers receive the same message in parallel.

    Each peer independently decides to either reply with content or
    return a bare ack.  The final response lists substantive replies
    and reports how many peers acked without contributing content.
    """

    plugin_id = "broadcast_ack@v1"
    mode = "broadcast_ack"

    def evaluate_next(self, q: QProduct, run: RunLedger, config: KernelConfig) -> list[EgressSymbol]:
        st = self._state()
        if not st.participants:
            return self._no_participants(q)

        tool_results = self._extract_tool_results(run)

        if st.round_num == 1 and st.next_idx == 0:
            st.next_idx = 1
            return dispatch_parallel(self, q, run, config, st.original_task, st.participants)

        replies = [r for r in tool_results if not _is_ack(r)]
        ack_count = len(tool_results) - len(replies)

        if not tool_results:
            return self._finish(q, "Broadcast complete (no responses received).")

        if not replies:
            suffix = f" [{ack_count} peer(s) acknowledged]" if ack_count else ""
            return self._finish(q, f"Broadcast acknowledged by all peers (no replies).{suffix}")

        parts: list[str] = [f"=== Reply {i + 1} ===\n{reply.strip()}" for i, reply in enumerate(replies)]
        if ack_count:
            parts.append(f"[{ack_count} peer(s) acknowledged without reply]")

        return self._finish(q, "\n\n".join(parts))
