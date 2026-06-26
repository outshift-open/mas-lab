#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for tutorial integration tests."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
import yaml

# Session-scoped daemon from tests/conftest.py (autouse) — mas-lab CLI subprocesses
# auto-start the daemon and register client sessions per process.

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
TUTORIALS = REPO_ROOT / "docs" / "tutorials"
T01 = TUTORIALS / "01-building-an-agent"
T02 = TUTORIALS / "02-creating-a-mas"
T03 = TUTORIALS / "03-experiments-and-analysis"


@pytest.fixture
def t01_dir():
    return T01


@pytest.fixture
def t02_dir():
    return T02


@pytest.fixture
def t03_dir():
    return T03


# ---------------------------------------------------------------------------
# Mock LLM response factory
# ---------------------------------------------------------------------------

@dataclass
class FakeLLMResponse:
    """Mimics mas.runtime.contracts.model_contract.LLMResponse."""
    content: str = "This is a mock LLM response."
    usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    })
    tool_calls: Optional[List[Dict[str, Any]]] = None
    thinking: Optional[str] = None
    finish_reason: Optional[str] = "stop"


def make_llm_response(content="Mock answer.", tool_calls=None, finish_reason="stop"):
    """Create a fake LLM response."""
    return FakeLLMResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
    )


@pytest.fixture
def fake_llm_response():
    """A simple mock LLM response with no tool calls."""
    return make_llm_response()


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# CLI runner helper
# ---------------------------------------------------------------------------

def run_cli(args: list[str], cwd: Path | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a CLI command and return the result.

    Resolves the command from the current Python environment's Scripts/bin
    directory so tests work inside a venv without requiring PATH changes.
    """
    # Resolve the executable from the same prefix as the running interpreter
    venv_bin = Path(sys.executable).parent
    exe = venv_bin / args[0]
    if exe.exists():
        resolved_args = [str(exe)] + args[1:]
    else:
        resolved_args = args

    return subprocess.run(
        resolved_args,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
        env={**os.environ, "MAS_MANIFEST_VALIDATE": "1"},
    )
