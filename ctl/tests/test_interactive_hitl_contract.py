#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""InteractiveHitlContract resolves via a simulated stdin answer instead of blocking
on a registry nothing in an interactive CLI session ever reads."""

from __future__ import annotations

import io

from mas.ctl.session.interactive_hitl_contract import InteractiveHitlContract


def test_prompts_and_returns_free_text_answer() -> None:
    out = io.StringIO()
    contract = InteractiveHitlContract(read_line=lambda _prompt: "go ahead", out=out)

    result = contract.request_approval(
        question="Should I proceed?",
        session_id="sess-1",
        requesting_user_id="jordan",
        agent_id="agent-a",
        correlation_id=1,
        question_type="FREE_TEXT",
        choices=[],
        context_data={},
    )

    assert result == {"choice": "go ahead", "steering": ""}
    assert "agent-a needs your input" in out.getvalue()
    assert "Should I proceed?" in out.getvalue()


def test_matches_choice_case_insensitively() -> None:
    contract = InteractiveHitlContract(read_line=lambda _prompt: "APPROVE", out=io.StringIO())

    result = contract.request_approval(
        question="Approve?",
        session_id="sess-2",
        requesting_user_id="jordan",
        agent_id="agent-a",
        correlation_id=1,
        question_type="CONFIRM",
        choices=["approve", "reject"],
        context_data={},
    )

    assert result["choice"] == "approve"


def test_passes_through_unrecognized_choice_as_free_text() -> None:
    contract = InteractiveHitlContract(read_line=lambda _prompt: "maybe later", out=io.StringIO())

    result = contract.request_approval(
        question="Approve?",
        session_id="sess-3",
        requesting_user_id="jordan",
        agent_id="agent-a",
        correlation_id=1,
        question_type="CONFIRM",
        choices=["approve", "reject"],
        context_data={},
    )

    assert result["choice"] == "maybe later"


def test_displays_context_and_choices() -> None:
    out = io.StringIO()
    contract = InteractiveHitlContract(read_line=lambda _prompt: "approve", out=out)

    contract.request_approval(
        question="Approve?",
        session_id="sess-4",
        requesting_user_id="jordan",
        agent_id="agent-a",
        correlation_id=1,
        question_type="CONFIRM",
        choices=["approve", "reject"],
        context_data={"amount": 42},
        timeout=5.0,
    )

    rendered = out.getvalue()
    assert "Context: {'amount': 42}" in rendered
    assert "Choices: approve, reject" in rendered
