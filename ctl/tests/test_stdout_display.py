#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io

from mas.ctl.ui.stdout import StdoutConversationDisplay


def test_on_user_echoes_without_trace():
    out = io.StringIO()
    display = StdoutConversationDisplay(out=out, verbose=1, show_labels=True, trace=False)
    display.on_user("What is the capital of France?")
    assert out.getvalue() == "You: What is the capital of France?\n"


def test_on_user_suppressed_when_trace_at_v1():
    out = io.StringIO()
    display = StdoutConversationDisplay(out=out, verbose=1, show_labels=True, trace=True)
    display.on_user("What is the capital of France?")
    assert out.getvalue() == ""


def test_on_user_kept_with_trace_at_vv():
    out = io.StringIO()
    display = StdoutConversationDisplay(out=out, verbose=2, show_labels=True, trace=True)
    display.on_user("What is the capital of France?")
    assert out.getvalue() == "You: What is the capital of France?\n"


def test_on_agent_suppressed_when_trace_at_v1():
    """--trace already prints the agent's answer via the exchange log --
    on_agent must not print it again as plain "Agent: text" duplication."""
    out = io.StringIO()
    display = StdoutConversationDisplay(out=out, verbose=1, show_labels=True, trace=True)
    display.on_agent("Paris.")
    assert out.getvalue() == ""


def test_on_agent_kept_with_trace_at_vv():
    out = io.StringIO()
    display = StdoutConversationDisplay(out=out, verbose=2, show_labels=True, trace=True)
    display.on_agent("Paris.")
    assert out.getvalue() == "Agent: Paris.\n\n"
