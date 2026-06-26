#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Smoke tests that the dev venv exposes lab subpackages (controller, bench, core)."""

from __future__ import annotations


def test_mas_lab_controller_importable() -> None:
    import mas.lab.controller  # noqa: F401
    from mas.lab.controller.daemon import main as daemon_main

    assert callable(daemon_main)


def test_mas_lab_bench_importable() -> None:
    from mas.lab.benchmark.experiment import ExperimentConfig  # noqa: F401

    assert ExperimentConfig is not None
