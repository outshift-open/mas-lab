#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS overlay $entry applies design_pattern only to workflow.entry."""

from __future__ import annotations

from pathlib import Path

from mas.lab.lab.config.scenario_loading import load_stacked_config

REPO = Path(__file__).resolve().parents[4]
MAS = REPO / "library-samples" / "apps" / "trip-planner" / "mas.yaml"


def _write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body, encoding="utf-8")


def test_entry_overlay_patches_workflow_entry_only(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pattern-cot.yaml",
        """
apiVersion: mas/v1
kind: Overlay
metadata:
  id: pattern-cot
spec:
  target:
    kind: MAS
  patch:
    agents:
      "$entry":
        design_pattern:
          type: cot
          config:
            max_steps: 10
""",
    )
    cfg, _ = load_stacked_config(MAS, ["pattern-cot"], overlays_dir=tmp_path, base_dir=tmp_path)
    by_id = {a["id"]: a for a in cfg["agents"]}
    assert cfg["workflow"]["entry"] == "moderator"
    assert by_id["moderator"]["design_pattern"]["type"] == "cot"
    assert "design_pattern" not in by_id["schedule_agent"]
    assert "design_pattern" not in by_id["itinerary_agent"]
    assert "design_pattern" not in by_id["concierge_agent"]


def test_entry_overlay_follows_workflow_from_an_earlier_overlay(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "shift-entry.yaml",
        """
apiVersion: mas/v1
kind: Overlay
metadata:
  id: shift-entry
spec:
  target:
    kind: MAS
  patch:
    workflow:
      entry: schedule_agent
      nodes:
        - id: schedule_agent
        - id: moderator
""",
    )
    _write(
        tmp_path,
        "pattern-react.yaml",
        """
apiVersion: mas/v1
kind: Overlay
metadata:
  id: pattern-react
spec:
  target:
    kind: MAS
  patch:
    agents:
      "$entry":
        design_pattern:
          type: react
""",
    )
    cfg, _ = load_stacked_config(
        MAS,
        ["shift-entry", "pattern-react"],
        overlays_dir=tmp_path,
        base_dir=tmp_path,
    )
    by_id = {a["id"]: a for a in cfg["agents"]}
    assert by_id["schedule_agent"]["design_pattern"]["type"] == "react"
    assert "design_pattern" not in by_id["moderator"]
