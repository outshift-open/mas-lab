#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Run-input tool fixture sidecars for mock tool providers."""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


_EVAL_ONLY_KEYS = ("correct_action", "source_evidence", "ground_truth")


def shared_tool_fixture_payload(tool_fixtures: Any) -> Any:
    """Payload every mock tool can share (``*`` / single file).

    Per-tool payloads stay in ``tool_fixtures["by_tool"]``. This helper only
    picks the shared document that today's SRE tools load from one file.
    """
    if not isinstance(tool_fixtures, dict):
        return tool_fixtures
    by_tool = tool_fixtures.get("by_tool")
    if isinstance(by_tool, dict) and by_tool:
        if "*" in by_tool:
            return by_tool["*"]
        first = next(iter(by_tool.values()))
        return first
    data = dict(tool_fixtures)
    for key in _EVAL_ONLY_KEYS:
        data.pop(key, None)
    return data


def write_tool_fixtures_sidecar(spec_path: Path, tool_fixtures: Any) -> None:
    """Hand the dataset item's payload to mock tools for this run.

    SRE mock tools currently load ``artifacts/scene.yaml``. That is an
    adapter for those tools, not a dataset concept.
    """
    if tool_fixtures is None:
        return

    sidecar_dir = spec_path.parent / "artifacts"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    payload = shared_tool_fixture_payload(tool_fixtures)
    if isinstance(tool_fixtures, dict) and isinstance(tool_fixtures.get("by_tool"), dict):
        mapping_path = sidecar_dir / "tool_fixtures.yaml"
        with open(mapping_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(tool_fixtures, fh, default_flow_style=False, allow_unicode=True)
    if not isinstance(payload, (dict, list)):
        payload = {"data": payload}
    sidecar_path = sidecar_dir / "scene.yaml"
    with open(sidecar_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, default_flow_style=False, allow_unicode=True)
    logger.debug("Wrote tool fixtures sidecar: %s", sidecar_path)
