#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Offline CI LLM: openai provider + strict llm_cache replay fixture."""

from __future__ import annotations

import json
from pathlib import Path

from mas.runtime.engine.simulated import SimulatedEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_REPLAY_YAML = REPO_ROOT / "tests" / "fixtures" / "llm-cache" / "ci-replay.yaml"
CI_WRITE_YAML = REPO_ROOT / "tests" / "fixtures" / "llm-cache" / "ci-write.yaml"
CI_CACHE_JSON = REPO_ROOT / "tests" / "fixtures" / "llm-cache" / "ci.llm-cache.json"


def ci_replay_refs() -> str:
    """``MAS_INFRA_REFS`` / ``--infra-ref`` value for offline CI replay."""
    return f"standard:openai,{CI_REPLAY_YAML.resolve()}"


def ci_write_refs(*, provider: str = "standard:openai") -> str:
    """Record into the CI fixture. ``provider`` is the inner LLM bundle."""
    return f"{provider},{CI_WRITE_YAML.resolve()}"


def ci_cache_ready() -> bool:
    if not CI_CACHE_JSON.is_file():
        return False
    try:
        data = json.loads(CI_CACHE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data)


def require_ci_cache() -> None:
    """Fail closed when the committed replay fixture is missing or empty."""
    if ci_cache_ready():
        return
    raise AssertionError(
        "tests/fixtures/llm-cache/ci.llm-cache.json is empty. "
        "Record it against a live provider: python scripts/record_ci_llm_cache.py"
    )


def mas_infra_refs_for_ci() -> str:
    """Always replay. An empty fixture fails the LLM turn (raise_on_miss)."""
    return ci_replay_refs()


def stop_engine(*, text: str = "ok") -> SimulatedEngine:
    """Deterministic engine for bootstrap tests that must not call a provider."""
    return SimulatedEngine(llm_next_step=lambda _cid: "STOP", stop_text=text)


def web_search_engine(
    *,
    query: str = "Who is POTUS",
    answer: str = "The current POTUS is a public office holder.",
) -> SimulatedEngine:
    """First LLM turn requests web-search; later turns stop with ``answer``."""

    def llm_next_step(cid: int) -> str:
        return "TOOL_CALL" if cid == 1 else "STOP"

    def llm_tool_intent(cid: int) -> tuple[str, dict]:
        if cid == 1:
            return "web-search", {"query": query}
        return "", {}

    return SimulatedEngine(
        llm_next_step=llm_next_step,
        llm_tool_intent=llm_tool_intent,
        stop_text=answer,
    )
