#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Verifier (propose-then-verify) deterministic design pattern."""

from __future__ import annotations

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.state import QProduct, RunLedger
from mas.runtime.schema.egress import EgressSymbol

from mas.library.standard.plugins.design_patterns.base import _DeterministicBase
from mas.library.standard.plugins.design_patterns.utils import dispatch_single


class DeterministicVerifierPlugin(_DeterministicBase):
    """Propose-then-verify — agent 0 proposes, agent 1 fact-checks the proposal."""

    plugin_id = "deterministic_verifier@v1"
    mode = "verifier"

    def evaluate_next(self, q: QProduct, run: RunLedger, *, config: KernelConfig) -> list[EgressSymbol]:
        st = self._state()
        if not st.participants:
            return self._no_participants(q)
        tool_results = self._extract_tool_results(run)

        if st.round_num == 1 and st.next_idx == 0:
            st.next_idx = 1
            return dispatch_single(self, q, run, config, st.original_task, st.participants[0])

        if st.round_num == 1:
            st.next_idx = 2
            st.round_num = 2
            proposal = tool_results[-1] if tool_results else ""
            verify_prompt = (
                "Review and verify the proposal below. Check facts, logic, and completeness.\n\n"
                f"Proposal:\n{proposal}"
            )
            target = st.participants[1] if len(st.participants) > 1 else st.participants[0]
            return dispatch_single(self, q, run, config, verify_prompt, target)

        return self._finish(q, tool_results[-1] if tool_results else "Verification complete.")


class DeterministicVerifierPlugin(_DeterministicBase):
    """Verifier — propose-then-verify pattern (agent 0 proposes, agent 1 verifies)."""
    
    plugin_id = "deterministic_verifier@v1"
    mode: Mode = "verifier"

    def handle_event(self, q: QProduct, run: RunLedger, event: IngressSymbol, *, config: KernelConfig) -> list[EgressSymbol]:
        return handle_event_deterministic(self, q, run, event, config=config)

    def on_user_input(self, ctx: QProduct, event: object) -> DpState:
        return DpState.CTX_BUILD

    def on_context_complete(self, ctx: QProduct):
        return DpState.EVALUATING, None

    def on_evaluate(self, ctx: QProduct):
        return DpState.EVALUATING, None

    def evaluate_next(self, ctx: QProduct, run: RunLedger, *, config: KernelConfig) -> list[EgressSymbol]:
        """Evaluate: propose-verify pattern (agent 0 proposes, agent 1 verifies)."""
        q = ctx
        st = self._state()

        if not st.participants:
            q.dp = DpState.IDLE
            q.scheduled_egress = "NONE"
            return emit_final("Deterministic run complete (no participants).")

        tool_results = self._extract_tool_results(run)

        if st.round_num == 1 and st.next_idx == 0:
            st.next_idx = 1
            target = st.participants[0] if st.participants else "proposer"
            return dispatch_single(self, q, run, config, st.original_task, target)
        
        if st.round_num == 1 and st.next_idx == 1:
            st.next_idx = 2
            st.round_num = 2
            proposal = tool_results[-1] if tool_results else ""
            verify_prompt = (
                "Review and verify the proposal below. Check facts, logic, and completeness.\n\n"
                f"Proposal:\n{proposal}"
            )
            target = st.participants[1] if len(st.participants) > 1 else "verifier"
            return dispatch_single(self, q, run, config, verify_prompt, target)
        
        q.dp = DpState.IDLE
        q.scheduled_egress = "NONE"
        txt = tool_results[-1] if tool_results else "Verification complete."
        return emit_final(txt)
