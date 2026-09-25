#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from jsonschema import Draft7Validator
from mas.ctl.validate.schemas import load_schema


def test_agent_schema_accepts_summarizer_model_override() -> None:
    schema = load_schema("agent")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "qa-agent"},
        "spec": {
            "description": "qa",
            "models": [
                {"id": "main", "model": "gpt-4o", "context_window": 128000, "max_tokens": 2000},
                {"id": "summarizer", "model": "gpt-4o-mini"},
            ],
            "context_manager": {
                "type": "summarising",
                "params": {
                    "keep_turns": 10,
                    "hysteresis_ratio": 0.2,
                    "summarizer": {
                        "type": "llm",
                        "params": {"model": "summarizer"},
                    },
                    "trimmer": {"max_tokens": 128000, "reserve_tokens": 2000},
                },
            },
            "working_memory": {
                "compaction": {
                    "strategy": "summarize",
                    "model": "gpt-4o-mini",
                    "keep_turns": 10,
                    "summary_threshold": 0,
                }
            },
        },
    }
    errors = list(Draft7Validator(schema).iter_errors(doc))
    assert errors == []


def test_agent_schema_accepts_summarizer_top_level_model_shorthand() -> None:
    schema = load_schema("agent")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "qa-agent"},
        "spec": {
            "description": "qa",
            "models": [{"model": "gpt-4o"}],
            "context_manager": {
                "type": "summarising",
                "params": {"summarizer": {"type": "llm", "model": "gpt-4o-mini"}},
            },
        },
    }
    errors = list(Draft7Validator(schema).iter_errors(doc))
    assert errors == []


def test_experiment_schema_accepts_evaluation_model() -> None:
    schema = load_schema("experiment")
    doc = {
        "experiment": {
            "name": "topology-ablation",
            "applications": [{"manifest": "./mas.yaml"}],
            "evaluation": {"method": "llm_judge", "model": "gpt-4o-mini"},
            "application": {
                "post": [
                    {"type": "eval_mce", "config": {"model": "gpt-4o"}},
                ]
            },
        }
    }
    errors = list(Draft7Validator(schema).iter_errors(doc))
    assert errors == []


def test_agent_schema_accepts_summarizer_instructions() -> None:
    schema = load_schema("agent")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "qa-agent"},
        "spec": {
            "description": "qa",
            "models": [{"model": "gpt-4o"}],
            "context_manager": {
                "type": "summarising",
                "params": {
                    "summarizer": {
                        "type": "llm",
                        "params": {
                            "model": "gpt-4o-mini",
                            "instructions": "Preserve city names.",
                        },
                    }
                },
            },
        },
    }
    errors = list(Draft7Validator(schema).iter_errors(doc))
    assert errors == []


def test_agent_schema_rejects_unknown_context_manager_param() -> None:
    schema = load_schema("agent")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "qa-agent"},
        "spec": {
            "description": "qa",
            "models": [{"model": "gpt-4o"}],
            "context_manager": {
                "type": "summarising",
                "params": {"keep_turns": 10, "sumarizer": "llm"},
            },
        },
    }
    errors = list(Draft7Validator(schema).iter_errors(doc))
    assert errors, "typo 'sumarizer' must be rejected at the params object"
