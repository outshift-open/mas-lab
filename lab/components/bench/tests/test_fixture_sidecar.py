from pathlib import Path

import yaml
from mas.lab.benchmark.runners.fixtures import write_tool_fixtures_sidecar


def test_legacy_fixture_sidecar_preserves_source_reference(tmp_path: Path) -> None:
    write_tool_fixtures_sidecar(
        tmp_path / "experiment.yaml",
        {"services": {}},
        source_ref="datasets/incidents/payment-async-timeout.yaml",
    )

    sidecar = yaml.safe_load(
        (tmp_path / "artifacts" / "scene.yaml").read_text(encoding="utf-8")
    )
    assert sidecar == {
        "incident_fixture": "datasets/incidents/payment-async-timeout.yaml"
    }


def test_inline_fixture_sidecar_remains_unchanged(tmp_path: Path) -> None:
    write_tool_fixtures_sidecar(tmp_path / "experiment.yaml", {"services": {}})

    sidecar = yaml.safe_load(
        (tmp_path / "artifacts" / "scene.yaml").read_text(encoding="utf-8")
    )
    assert sidecar == {"services": {}}