from mas.library.standard.plugins.design_patterns.parallel import (
    DeterministicParallelPlugin,
)
from mas.runtime.kernel.config import KernelConfig


def _participants(agent_spec: dict) -> list[str]:
    config = KernelConfig(agent_spec=agent_spec)
    return DeterministicParallelPlugin()._participants_from_spec(config)


def test_participants_follow_configured_entry_delegates() -> None:
    assert _participants(
        {
            "workflow": {
                "entry": "sre",
                "nodes": [
                    {
                        "id": "sre",
                        "delegates_to": ["telemetry", "backend", "verifier"],
                    },
                    {"id": "telemetry"},
                    {"id": "backend"},
                    {"id": "verifier"},
                ],
            }
        }
    ) == ["telemetry", "backend", "verifier"]


def test_participant_sources_exclude_configured_entry() -> None:
    assert _participants(
        {
            "workflow": {
                "entry": "lead",
                "participants": ["lead", "analyst", "verifier"],
            }
        }
    ) == ["analyst", "verifier"]

    assert _participants(
        {
            "workflow": {
                "entry": "lead",
                "nodes": [
                    {"id": "lead"},
                    {"id": "analyst"},
                    {"id": "verifier"},
                ],
            }
        }
    ) == ["analyst", "verifier"]

    assert _participants(
        {
            "workflow": {"entry": "lead"},
            "agency": {
                "agents": [
                    {"id": "lead"},
                    {"id": "analyst"},
                    {"id": "verifier"},
                ]
            },
        }
    ) == ["analyst", "verifier"]


def test_moderator_remains_default_entry() -> None:
    assert _participants(
        {
            "workflow": {
                "nodes": [
                    {
                        "id": "moderator",
                        "delegates_to": ["analyst", "verifier"],
                    },
                    {"id": "analyst"},
                    {"id": "verifier"},
                ]
            }
        }
    ) == ["analyst", "verifier"]
