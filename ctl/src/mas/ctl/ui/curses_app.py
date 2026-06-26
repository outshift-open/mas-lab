#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Curses TUI — SessionController backend with infra sidebar."""

from __future__ import annotations

import curses

from mas.runtime.schema.hitl import HitlResolveChoice

from mas.ctl.session.controller import ConversationConfig, SessionController

_BTN_STOP = 0
_BTN_RESUME = 1
_BTN_ABORT = 2
_TOOLBAR_LABELS = (
    (" STOP ", _BTN_STOP),
    (" RESUME ", _BTN_RESUME),
    (" ABORT ", _BTN_ABORT),
)


def run_curses_session(
    controller: SessionController,
    *,
    infra_lines: list[str] | None = None,
) -> None:
    """Blocking curses loop; drives controller with auto_hitl=False for HITL panes."""
    infra = infra_lines or ["infra: (none)"]
    transcript: list[str] = []
    status = "Tab=controls  Enter=send  F6/F7/F8=lifecycle  /quit=exit"
    input_buffer = ""
    hitl_request = None
    paused = False
    btn_focus: int | None = None
    btn_regions: list[tuple[int, int, int]] = []

    class _Display:
        def on_user(self, text: str, *, turn_id: str = "") -> None:
            transcript.append(f"You: {text}")

        def on_agent(self, text: str) -> None:
            if text.strip():
                transcript.append(f"Agent: {text}")

        def on_hitl_request(self, request) -> None:
            nonlocal hitl_request
            hitl_request = request
            offered = ", ".join(a.value for a in request.offered_actions)
            transcript.append(f"[HITL #{request.request_id}: {offered}]")

        def on_system(self, message: str) -> None:
            nonlocal status, paused
            status = message
            low = message.lower()
            if "paused" in low:
                paused = True
            elif "resumed" in low:
                paused = False
            elif "aborted" in low:
                paused = False

        def on_turn_error(self, message: str, *, detail: str = "") -> None:
            line = f"ERROR: {message}"
            if detail.strip() and detail.strip() != message.strip():
                line = f"{line} ({detail.strip()})"
            transcript.append(line)

        def on_error(self, message: str) -> None:
            self.on_turn_error(message)

    controller.display = _Display()

    def _toolbar_row(h: int) -> int:
        return h - 2

    def _draw_toolbar(stdscr: curses.window, h: int, w: int) -> None:
        nonlocal btn_regions
        row = _toolbar_row(h)
        btn_regions = []
        x = 0
        for label, bid in _TOOLBAR_LABELS:
            end = min(x + len(label), w - 1)
            if x >= w - 1:
                break
            attr = curses.A_NORMAL
            if btn_focus == bid:
                attr = curses.A_REVERSE | curses.A_BOLD
            elif bid == _BTN_STOP and paused:
                attr = curses.A_BOLD
            stdscr.addnstr(row, x, label[: end - x], end - x, attr)
            btn_regions.append((x, end, bid))
            x = end + 1

    def _draw(stdscr: curses.window) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        sidebar_w = min(28, w // 3)
        main_w = max(20, w - sidebar_w)
        stdscr.addstr(0, 0, " chat ", curses.A_REVERSE)
        stdscr.addstr(0, main_w, " infra ", curses.A_REVERSE)
        body_h = h - 4
        for i, line in enumerate(transcript[-body_h:]):
            stdscr.addnstr(i + 1, 0, line, main_w - 1)
        for i, line in enumerate(infra[: body_h - 1]):
            stdscr.addnstr(i + 1, main_w + 1, line, sidebar_w - 2)
        prompt = "HITL> " if hitl_request else "> "
        input_attr = curses.A_REVERSE if btn_focus is None else curses.A_NORMAL
        stdscr.addnstr(h - 3, 0, f"{prompt}{input_buffer}", w - 2, input_attr)
        _draw_toolbar(stdscr, h, w)
        stdscr.addnstr(h - 1, 0, status[: w - 1], w - 1)
        stdscr.refresh()

    def _activate_button(bid: int) -> None:
        nonlocal status, paused
        if bid == _BTN_STOP:
            controller.instance.pause()
            paused = True
            status = "paused — RESUME or /resume"
        elif bid == _BTN_RESUME:
            controller.instance.resume()
            paused = False
            status = "Tab=controls  Enter=send  F6/F7/F8=lifecycle  /quit=exit"
        elif bid == _BTN_ABORT:
            controller.instance.abort()
            paused = False
            status = "aborted — continue or /quit"

    def _button_at(mx: int) -> int | None:
        for x0, x1, bid in btn_regions:
            if x0 <= mx < x1:
                return bid
        return None

    def _loop(stdscr: curses.window) -> None:
        nonlocal input_buffer, hitl_request, status, btn_focus, paused
        curses.curs_set(1)
        stdscr.keypad(True)
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        except curses.error:
            pass
        pending: TurnResult | None = None

        while True:
            _draw(stdscr)
            ch = stdscr.getch()
            if ch in (3, 26):
                break
            if ch == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, _ = curses.getmouse()
                    h, _ = stdscr.getmaxyx()
                    if my == _toolbar_row(h):
                        bid = _button_at(mx)
                        if bid is not None:
                            _activate_button(bid)
                except curses.error:
                    pass
                continue
            if ch == 9:  # Tab
                if btn_focus is None:
                    btn_focus = _BTN_STOP
                elif btn_focus == _BTN_STOP:
                    btn_focus = _BTN_RESUME
                elif btn_focus == _BTN_RESUME:
                    btn_focus = _BTN_ABORT
                else:
                    btn_focus = None
                continue
            if ch == curses.KEY_F6:
                _activate_button(_BTN_STOP)
                continue
            if ch == curses.KEY_F7:
                _activate_button(_BTN_RESUME)
                continue
            if ch == curses.KEY_F8:
                _activate_button(_BTN_ABORT)
                continue
            if ch in (curses.KEY_ENTER, 10, 13):
                if btn_focus is not None:
                    _activate_button(btn_focus)
                    continue
                if hitl_request is not None:
                    raw = input_buffer.strip().upper() or HitlResolveChoice.ALLOW.value
                    input_buffer = ""
                    from mas.ctl.session.hitl_prompt import build_hitl_resolve

                    resolve = build_hitl_resolve(
                        hitl_request,
                        raw,
                        operator_id="curses",
                    )
                    pending = controller.submit_hitl(resolve, auto_hitl=False)
                    hitl_request = None
                    if pending.awaiting_hitl and pending.trace.hitl_requests:
                        hitl_request = pending.trace.hitl_requests[-1]
                    if controller.config.single_turn and not pending.awaiting_hitl:
                        break
                    continue
                text = input_buffer.strip()
                input_buffer = ""
                if not text:
                    continue
                if text.lower() in ("/quit", "/exit", "/q"):
                    break
                if text.lower() == "/resume":
                    _activate_button(_BTN_RESUME)
                    continue
                if text.lower() in ("/pause", "/stop"):
                    _activate_button(_BTN_STOP)
                    continue
                if text.lower() in ("/abort", "/kill"):
                    _activate_button(_BTN_ABORT)
                    continue
                pending = controller.run_turn(text, auto_hitl=False)
                if pending.awaiting_hitl and pending.trace.hitl_requests:
                    hitl_request = pending.trace.hitl_requests[-1]
                if controller.config.single_turn and not pending.awaiting_hitl:
                    break
                continue
            if btn_focus is not None:
                if ch in (curses.KEY_LEFT, ord("h")):
                    btn_focus = max(0, (btn_focus or 0) - 1)
                    continue
                if ch in (curses.KEY_RIGHT, ord("l")):
                    btn_focus = min(_BTN_ABORT, (btn_focus or 0) + 1)
                    continue
            if ch in (8, 127, curses.KEY_BACKSPACE):
                input_buffer = input_buffer[:-1]
            elif btn_focus is None and 32 <= ch <= 126:
                input_buffer += chr(ch)

    from mas.ctl.session.controller import TurnResult  # noqa: F401 — used in annotation

    curses.wrapper(_loop)


def build_curses_controller(
    instance,
    *,
    single_turn: bool = False,
) -> SessionController:
    
    return SessionController(
        instance=instance,
        display=_NullDisplay(),
        config=ConversationConfig(single_turn=single_turn),
    )


class _NullDisplay:
    def on_user(self, text: str, *, turn_id: str = "") -> None:
        pass

    def on_agent(self, text: str) -> None:
        pass

    def on_hitl_request(self, request) -> None:
        pass

    def on_system(self, message: str) -> None:
        pass

    def on_error(self, message: str) -> None:
        pass
