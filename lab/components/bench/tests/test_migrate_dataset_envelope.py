#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Migration script must keep extra user turns, matching the runtime loader."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _mod():
    path = (
        Path(__file__).resolve().parents[4] / "scripts" / "migrate_dataset_envelope.py"
    )
    spec = importlib.util.spec_from_file_location("migrate_dataset_envelope", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_migrate_keeps_extra_user_turns_and_hitl():
    migrate = _mod()
    out = migrate._migrate_item(
        {
            "id": "q1",
            "prompt": "First",
            "turns": [
                {"role": "user", "content": "Second"},
                {"role": "hitl", "content": "Approve"},
            ],
        }
    )
    assert out["inputs"]["user"] == ["First", "Second"]
    assert out["inputs"]["hitl"] == ["Approve"]
