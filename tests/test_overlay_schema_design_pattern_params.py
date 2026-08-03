#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from mas.ctl.validate.schemas import load_schema
from jsonschema import Draft7Validator


def test_overlay_schema_rejects_global_design_pattern_params_on_mas_target() -> None:
    schema = load_schema("overlay")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "dp-params"},
        "spec": {
            "target": {"kind": "MAS"},
            "patch": {
                "design_pattern": {
                    "type": "concord",
                    "params": {
                        "max_rounds": 3,
                        "enable_peer_context": False,
                    },
                }
            },
        },
    }

    errors = sorted(Draft7Validator(schema).iter_errors(doc), key=lambda e: e.path)
    assert errors


def test_overlay_schema_rejects_agent_only_patch_on_flavour_target() -> None:
    schema = load_schema("overlay")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "bad-flavour-patch"},
        "spec": {
            "target": {"kind": "Flavour"},
            "patch": {
                "design_pattern": {
                    "type": "concord",
                }
            },
        },
    }

    errors = sorted(Draft7Validator(schema).iter_errors(doc), key=lambda e: e.path)
    assert errors


def test_overlay_schema_accepts_explicit_collection_ops_for_agent_target() -> None:
    schema = load_schema("overlay")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "agent-ops"},
        "spec": {
            "target": {"kind": "Agent"},
            "patch": {
                "tools": {"$op": {"add": ["calc"], "remove": ["web-search"]}},
                "skills": {"$op": {"replace": ["route-planning"]}},
                "infra_refs": {"$op": {"clear": True, "add": ["standard:mock-llm"]}},
            },
        },
    }

    errors = sorted(Draft7Validator(schema).iter_errors(doc), key=lambda e: e.path)
    assert not errors, [e.message for e in errors]


def test_overlay_schema_accepts_agents_remove_ops_for_mas_target() -> None:
    schema = load_schema("overlay")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "mas-ops"},
        "spec": {
            "target": {"kind": "MAS"},
            "patch": {
                "agents_remove": {"$op": {"add": ["generalist"]}},
                "workflow": {"type": "single", "entry": "generalist"},
            },
        },
    }

    errors = sorted(Draft7Validator(schema).iter_errors(doc), key=lambda e: e.path)
    assert not errors, [e.message for e in errors]


def test_overlay_schema_rejects_missing_target_kind() -> None:
    schema = load_schema("overlay")
    doc = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "missing-target"},
        "spec": {
            "patch": {
                "skills": {"$op": {"add": ["route-planning"]}},
            },
        },
    }

    errors = sorted(Draft7Validator(schema).iter_errors(doc), key=lambda e: e.path)
    assert errors
