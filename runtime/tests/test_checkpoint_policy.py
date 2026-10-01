#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest

from mas.runtime.spec.checkpoint import CheckpointPolicy, CheckpointSpecError, parse_checkpoint_policy
from mas.runtime.spec.parser import parse_agent_spec


def test_checkpoint_policy_defaults_preserve_existing_behavior() -> None:
    assert parse_checkpoint_policy(None) == CheckpointPolicy()
    parse_agent_spec({"checkpoint": {"mode": "none"}})


def test_checkpoint_policy_parses_cadence_and_retention() -> None:
    policy = parse_checkpoint_policy(
        {
            "mode": "on_event",
            "triggers": ["after_llm_call", "every_n_turns"],
            "every_n_turns": 4,
            "retention": {"mode": "last_n", "n": 7},
            "auto_resume_latest": True,
        }
    )

    assert policy.mode == "on_event"
    assert policy.triggers == ("after_llm_call", "every_n_turns")
    assert policy.retention_mode == "last_n"
    assert policy.retention_n == 7
    assert policy.auto_resume_latest is True


@pytest.mark.parametrize(
    "raw",
    [
        {"mode": "unknown"},
        {"triggers": ["not-an-event"]},
        {"every_n_turns": True},
        {"retention": {"mode": "last_n", "n": 0}},
        {"auto_resume_latest": "true"},
        {"mode": "in_memory", "auto_resume_latest": True},
        {"unexpected": True},
    ],
)
def test_checkpoint_policy_rejects_malformed_values(raw: dict) -> None:
    with pytest.raises(CheckpointSpecError):
        parse_agent_spec({"checkpoint": raw})