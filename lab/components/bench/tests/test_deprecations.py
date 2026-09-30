#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import yaml

from mas.lab.benchmark.dataset import Dataset
from mas.lab.deprecations import clear_deprecation_warnings, docs_url, warn_deprecated
from mas.lab.inputs import load_run_input
from mas.lab.lab.config import MASExperimentConfig


def setup_function() -> None:
    clear_deprecation_warnings()


def test_docs_url_strips_md_and_keeps_fragment() -> None:
    assert (
        docs_url("manifests/dataset-migration.md")
        == "https://outshift-open.github.io/mas-lab/manifests/dataset-migration/"
    )
    assert (
        docs_url("manifests/experiment.md#applications")
        == "https://outshift-open.github.io/mas-lab/manifests/experiment/#applications"
    )


def test_warn_deprecated_once_per_where(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="mas.lab.deprecations"):
        warn_deprecated("dataset.legacy_item", where="a.yaml")
        warn_deprecated("dataset.legacy_item", where="a.yaml")
        warn_deprecated("dataset.legacy_item", where="b.yaml")
    assert caplog.text.count("dataset.legacy_item") == 2
    assert "dataset-migration" in caplog.text


def test_legacy_prompt_item_warns_with_docs_url(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="mas.lab.deprecations"):
        run = load_run_input({"id": "001", "prompt": "legacy prompt"})
    assert run.primary_prompt == "legacy prompt"
    assert "dataset.legacy_item" in caplog.text
    assert "https://outshift-open.github.io/mas-lab/manifests/dataset-migration/" in caplog.text
    assert "docs/manifests/dataset-migration.md" in caplog.text


def test_role_list_user_warns(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="mas.lab.deprecations"):
        run = load_run_input(
            {
                "id": "legacy",
                "inputs": {"user": [{"role": "user", "content": "Old shape"}]},
            }
        )
    assert run.primary_prompt == "Old shape"
    assert "dataset.role_list_user" in caplog.text
    assert "dataset-migration" in caplog.text


def test_incident_fixture_warns(tmp_path: Path, caplog) -> None:
    (tmp_path / "scene.yaml").write_text("services: {}\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="mas.lab.deprecations"):
        load_run_input(
            {
                "id": "x",
                "inputs": {
                    "user": "Q",
                    "tool_fixtures": {"incident_fixture": "scene.yaml"},
                },
            },
            base_path=tmp_path,
        )
    assert "dataset.incident_fixture" in caplog.text


def test_incident_fixture_retains_source_reference(tmp_path: Path) -> None:
    (tmp_path / "scene.yaml").write_text("services: {}\n", encoding="utf-8")

    run = load_run_input(
        {
            "id": "x",
            "inputs": {
                "user": "Q",
                "tool_fixtures": {"incident_fixture": "scene.yaml"},
            },
        },
        base_path=tmp_path,
    )

    assert run.tool_fixtures == {"services": {}}
    assert run.tool_fixture_ref == "scene.yaml"


def test_bare_list_dataset_warns(tmp_path: Path, caplog) -> None:
    path = tmp_path / "queries.yaml"
    yaml.dump([{"id": "q1", "prompt": "Q1"}], path.open("w"))
    with caplog.at_level(logging.WARNING, logger="mas.lab.deprecations"):
        dataset = Dataset.from_yaml(path)
    assert [item.prompt for item in dataset] == ["Q1"]
    assert "dataset.bare_list" in caplog.text
    assert "dataset.legacy_item" in caplog.text


def test_legacy_mas_key_warns(tmp_path: Path, caplog) -> None:
    mas_yaml = tmp_path / "mas.yaml"
    mas_yaml.write_text("apiVersion: mas/v1\nkind: MAS\nmetadata:\n  name: test\n")
    exp_yaml = tmp_path / "experiment.yaml"
    exp_yaml.write_text(
        textwrap.dedent(
            """\
            experiment:
              name: legacy-mas
              description: "Existing labs still use mas:"
              mas:
                manifest: ./mas.yaml
                configs_dir: ./overlays
            """
        )
    )
    with caplog.at_level(logging.WARNING, logger="mas.lab.deprecations"):
        cfg = MASExperimentConfig.from_yaml(exp_yaml)
    assert cfg.mas is not None
    assert "experiment.mas" in caplog.text
    assert "manifests/experiment/#applications" in caplog.text
