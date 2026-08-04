#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Session controller — ctl drives runtime via Σ_in; shared by stdout and curses UI."""

from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from mas.runtime.boundary.context.working_memory_registry import (
    get_working_memory_registry,
    sync_working_memory_in,
    sync_working_memory_out,
)
from mas.runtime.driver.driver import DriverTrace
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.schema.egress import EmitClientResponse

from mas.ctl.session.exchange_log import (
    TraceFormatOptions,
    print_exchange,
)
from mas.ctl.ui.display import ConversationDisplay


@dataclass
class ConversationConfig:
    single_turn: bool = False
    save_checkpoint_each_turn: bool = False
    checkpoint_label_prefix: str = "turn"


@dataclass
class TurnResult:
    trace: DriverTrace
    responses: list[EmitClientResponse] = field(default_factory=list)
    awaiting_hitl: bool = False

    @property
    def text(self) -> str:
        parts = [r.content for r in self.responses if getattr(r, "content", "")]
        return "\n".join(parts).strip()


@dataclass
class SessionController:
    """Ctl control-plane session — same backend for CLI, curses, REST/WS adapters."""

    instance: RuntimeInstance
    display: ConversationDisplay
    hitl_terminal: Any | None = None
    checkpoint_store: Any | None = None
    config: ConversationConfig = field(default_factory=ConversationConfig)
    verbose: int = 0
    trace: bool = False
    trace_timestamps: bool = False
    trace_engine: bool = False
    trace_summary: bool = False
    trace_color: bool = False
    agent_id: str = "n/a"
    llm_id: str = "gpt-4o-mini"
    obs_recorder: Any | None = None
    # One id for the whole MAS run — every turn this controller ever runs
    # shares it (see _run_user_turn). Empty here means "mint a fresh one";
    # explicitly pass an existing value (e.g. from an entry agent's own
    # SessionController, threaded through make_workflow_send) to make a
    # delegated agent's calls part of that SAME session instead of starting
    # a new one — session_id is global to the MAS, unlike each turn's own
    # task_id, which stays local to whichever agent runs it.
    session_id: str = ""
    # Overrides session_id as the WorkingMemoryRegistry key for this
    # controller's own agent (see _working_memory_key). Empty (the default,
    # every direct/chat controller) means "use session_id" — set explicitly
    # by make_workflow_send for a delegated call whose LLM-supplied
    # context_id should pick an independent bucket from the session default.
    working_memory_key: str = ""
    _turn: int = 0
    _trace_turn_start: float = 0.0

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = str(uuid.uuid4())

    def _working_memory_key(self) -> str:
        return self.working_memory_key or self.session_id

    def _trace_format_options(self) -> TraceFormatOptions:
        return TraceFormatOptions(
            timestamps=self.trace_timestamps,
            engine_io=self.trace_engine,
            summary_only=self.trace_summary,
            turn_start_mono=self._trace_turn_start,
            color=self.trace_color,
            agent_name=self.agent_id,
            llm_name=self.llm_id,
        )

    def _setup_exchange_tracing(self) -> None:
        """Setup realtime exchange tracing via driver callback (if trace or verbose)."""
        # Skip if neither trace nor verbose logging requested
        if not self.trace and self.verbose < 1:
            self.instance.driver.on_exchange = None
            self.instance.driver.capture_engine_io = False
            return

        self._trace_turn_start = time.perf_counter()
        self.instance.driver.capture_engine_io = self.trace_engine
        fmt = self._trace_format_options()
        logger = __import__("logging").getLogger("mas.runtime")

        def on_exchange(ex: object) -> None:
            from mas.runtime.driver.driver import ExchangeRecord
            from mas.ctl.session.exchange_log import format_exchange

            if not isinstance(ex, ExchangeRecord):
                return

            # Realtime stderr output (if --trace) — primary display path
            if self.trace:
                print_exchange(ex, err=sys.stderr, agent_id=self.agent_id, fmt=fmt)
            # Verbose logging only if NOT using --trace (alternative logging path)
            elif self.verbose >= 1:
                formatted = format_exchange(self.agent_id, ex, fmt=fmt).strip()
                for line in formatted.splitlines():
                    logger.info("[%s] %s", self.agent_id, line)

        self.instance.driver.on_exchange = on_exchange

    def reset_session(self) -> bool:
        """Clear working memory and turn history; restore baseline system prompt."""
        try:
            self.instance.reset_session()
        except RuntimeError as exc:
            self.display.on_system(str(exc))
            return False
        # Drop this agent's registry snapshot too -- otherwise the *next*
        # turn's sync_working_memory_in() would restore the pre-reset
        # history right back, silently undoing the reset the user just asked
        # for (see docs/design/working-memory-compaction.md).
        get_working_memory_registry().drop(self._working_memory_key(), self.agent_id)
        self._turn = 0
        self.display.on_system(
            "session reset — working memory and turn history cleared; system prompt restored"
        )
        return True

    def _finalize_turn(self, result: TurnResult, *, trace: DriverTrace | None = None) -> None:
        """Commit completed turn to ctx (chat history + tool trajectory).

        Folds working memory into committed history whenever there's
        anything to fold — a final response, tool calls that already ran
        this turn, or both — even when the turn is still paused awaiting
        HITL. Whatever already executed this turn (e.g. a delegated
        sub-agent's tool calls before an approval gate) is real conversation
        content: it must not be silently dropped the moment the *next* turn
        starts and ``note_user_input()`` clears working memory (see
        ``docs/design/working-memory-compaction.md``). Checkpointing is
        unaffected — still only for a turn that actually completed.
        """
        response_text = result.text
        ctx = getattr(self.instance.driver, "ctx", None)
        note_resp = getattr(ctx, "note_agent_response", None)
        has_working_memory = bool(
            getattr(getattr(ctx, "working_memory", None), "messages", None)
        )
        if callable(note_resp) and (response_text or has_working_memory):
            note_resp(response_text)
        sync_working_memory_out(
            self.instance, memory_key=self._working_memory_key(), agent_id=self.agent_id
        )
        if result.awaiting_hitl:
            return
        if self.config.save_checkpoint_each_turn and self.checkpoint_store is not None:
            snap = self.instance.record_checkpoint(
                f"{self.config.checkpoint_label_prefix}-{self._turn}"
            )
            self.checkpoint_store.save(snap)

    def run_turn(
        self,
        text: str,
        *,
        turn_id: str | None = None,
        auto_hitl: bool = True,
        parent_call_id: str = "",
    ) -> TurnResult:
        from mas.runtime.schema.ingress import OperatorSteerReceived

        if text.strip().lower().startswith("/steer "):
            steer_text = text.strip()[7:].strip()
            self._turn += 1
            tid = turn_id or f"steer{self._turn}"
            self.display.on_system(f"operator steer: {steer_text}")
            self._setup_exchange_tracing()
            trace = self.instance.feed(
                OperatorSteerReceived(steer_id=tid, context_text=steer_text)
            )
            if auto_hitl:
                trace = self._drain_hitl(trace)
            self._present_trace(trace)
            return TurnResult(trace=trace, responses=list(trace.client_responses))
        return self._run_user_turn(
            text, turn_id=turn_id, auto_hitl=auto_hitl, parent_call_id=parent_call_id
        )

    def _run_user_turn(
        self,
        text: str,
        *,
        turn_id: str | None = None,
        auto_hitl: bool = True,
        parent_call_id: str = "",
    ) -> TurnResult:
        from mas.ctl.manifest.mas_agent_merge import reset_engine_delegation

        reset_engine_delegation(getattr(self.instance.driver, "engine", None))
        sync_working_memory_in(
            self.instance, memory_key=self._working_memory_key(), agent_id=self.agent_id
        )
        self._turn += 1
        tid = turn_id or f"u{self._turn}"
        self.display.on_user(text, turn_id=tid)
        on_working = getattr(self.display, "on_working", None)
        if callable(on_working):
            on_working()
        self._setup_exchange_tracing()
        trace = self.instance.run_user_text(
            text, turn_id=tid, parent_call_id=parent_call_id, session_id=self.session_id
        )
        end_working = getattr(self.display, "end_working", None)
        if callable(end_working):
            end_working()
        while True:
            if auto_hitl:
                trace = self._drain_hitl(trace)
            if not auto_hitl:
                break
            if not self._session_awaiting_operator():
                break
            if self.hitl_terminal is None or not trace.hitl_requests:
                break
        self._present_trace(trace)
        result = TurnResult(
            trace=trace,
            responses=list(trace.client_responses),
            awaiting_hitl=trace.awaiting_hitl,
        )
        self._finalize_turn(result, trace=trace)
        return result

    def submit_hitl(self, resolve, *, auto_hitl: bool = True) -> TurnResult:
        """Feed HITL_RESOLVE after UI collects operator choice."""
        self._setup_exchange_tracing()
        trace = self.instance.feed(resolve)
        if auto_hitl:
            trace = self._drain_hitl(trace)
        self._present_trace(trace)
        result = TurnResult(
            trace=trace,
            responses=list(trace.client_responses),
            awaiting_hitl=trace.awaiting_hitl,
        )
        self._finalize_turn(result, trace=trace)
        return result

    def _drain_hitl(self, trace: DriverTrace) -> DriverTrace:
        while trace.awaiting_hitl and self.hitl_terminal is not None:
            if not trace.hitl_requests:
                break
            request = trace.hitl_requests[-1]
            self.display.on_hitl_request(request)
            resolve = self.hitl_terminal.resolve(request)
            trace = self.instance.feed(resolve)
        return trace

    def _present_trace(self, trace: DriverTrace) -> None:
        # HITL already drained in _drain_hitl; do not re-print pending requests.
        if not self.trace:
            for resp in trace.client_responses:
                self._present_client_response(resp)
        for err in trace.boundary_errors:
            self._present_boundary_error(err)

    def _present_client_response(self, resp: EmitClientResponse) -> None:
        if resp.finish_reason == "error":
            self.display.on_turn_error(resp.content)
        elif resp.content.strip():
            self.display.on_agent(resp.content)

    def _present_boundary_error(self, err: object) -> None:
        code = getattr(err, "code", str(err))
        message = getattr(err, "message", "") or ""
        if message.strip():
            self.display.on_turn_error(message.strip(), detail=str(code))
        else:
            self.display.on_turn_error(str(code))

    def _session_awaiting_operator(self) -> bool:
        from mas.runtime.machines.gov import gov_is_hitl_pending

        return gov_is_hitl_pending(self.instance.kernel.q)


def close_observability(controller: SessionController) -> None:
    if controller.obs_recorder is not None:
        controller.obs_recorder.close()
    elif hasattr(controller.instance, "obs_plugin_set") and controller.instance.obs_plugin_set:
        controller.instance.obs_plugin_set.close()


def run_session_loop(
    controller: SessionController,
    *,
    interactive: bool,
    scripted: list[str],
) -> int:
    """Single entry for ctl stdout executors. Returns process exit code (0 = ok)."""
    from mas.ctl.ui.turn_result import turn_failed

    if interactive:
        from mas.ctl.session.operator_console import OperatorConsole

        OperatorConsole().run(
            controller,
            initial=scripted[0] if scripted else None,
        )
        return 0
    exit_code = 0
    for text in scripted:
        if turn_failed(controller.run_turn(text)):
            exit_code = 1
    return exit_code
