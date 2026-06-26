#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Lab manifest validation — refs resolve and composed MAS builds."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_LABS = _ROOT / "labs"


def _experiment_paths() -> list[Path]:
    return sorted(_LABS.glob("**/experiment.yaml"))


def _lab_yaml_paths() -> list[Path]:
    return sorted(_LABS.glob("**/lab-config.yaml"))


@pytest.mark.parametrize("path", _experiment_paths(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_lab_experiment_refs_and_composition(path: Path) -> None:
    pytest.importorskip("jsonschema")
    from mas.lab.manifests.validator import validate_manifest

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    validate_manifest(
        data,
        source=str(path.relative_to(_ROOT)),
        kind="experiment",
        strict=True,
        resolve_refs=True,
        base_dir=path.parent,
    )


@pytest.mark.parametrize("path", _lab_yaml_paths(), ids=lambda p: str(p.relative_to(_ROOT)))
def test_lab_yaml_schema_and_refs(path: Path) -> None:
    pytest.importorskip("jsonschema")
    from mas.lab.manifests.validator import validate_manifest

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    validate_manifest(
        data,
        source=str(path.relative_to(_ROOT)),
        kind="lab",
        strict=True,
        resolve_refs=True,
        base_dir=path.parent,
    )


def test_missing_ref_fails_validation(tmp_path: Path) -> None:
    from mas.lab.manifests.validator import ManifestValidationError, validate_manifest

    exp = tmp_path / "experiment.yaml"
    exp.write_text(
        "experiment:\n  name: x\n  mas:\n    manifest: ./no-such-mas.yaml\n",
        encoding="utf-8",
    )
    data = yaml.safe_load(exp.read_text()) or {}
    with pytest.raises(ManifestValidationError, match="not found"):
        validate_manifest(
            data,
            source=str(exp),
            kind="experiment",
            strict=True,
            resolve_refs=True,
            base_dir=tmp_path,
        )


def test_composed_mas_tree_rejects_workflow_agent_mismatch() -> None:
    from mas.lab.manifests.composed_manifest import validate_composed_mas_tree

    mas_doc = {
        "apiVersion": "mas/v1",
        "kind": "MAS",
        "metadata": {"name": "t"},
        "spec": {
            "agency": {
                "agents": [
                    {
                        "apiVersion": "mas/v1",
                        "kind": "Agent",
                        "metadata": {"name": "schedule"},
                        "spec": {"design_pattern": {"type": "react"}, "role": {"description": "d"}},
                    }
                ]
            },
            "workflow": {"entry": "schedule_agent", "nodes": [{"id": "schedule_agent"}]},
        },
    }
    violations = validate_composed_mas_tree(mas_doc, label="test", mas_dir=Path("."))
    assert violations, violations


def test_bad_overlay_id_blocks_composition(tmp_path: Path) -> None:
    from mas.lab.manifests.validator import ManifestValidationError, validate_manifest

    mas_dir = tmp_path / "app"
    (mas_dir / "overlays").mkdir(parents=True)
    (mas_dir / "mas.yaml").write_text(
        "kind: MAS\nmetadata:\n  name: t\nspec:\n  agency:\n    agents: []\n",
        encoding="utf-8",
    )
    exp = tmp_path / "experiment.yaml"
    exp.write_text(
        "experiment:\n  name: x\n  mas:\n    manifest: ./app/mas.yaml\n"
        "    configs_dir: ./app/overlays\n  scenarios:\n    - id: missing\n",
        encoding="utf-8",
    )
    data = yaml.safe_load(exp.read_text()) or {}
    with pytest.raises(ManifestValidationError):
        validate_manifest(
            data,
            source=str(exp),
            kind="experiment",
            strict=True,
            resolve_refs=True,
            base_dir=tmp_path,
        )
