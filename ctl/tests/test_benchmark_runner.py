#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Bench runner identity — stable runner_id for analytics."""

from mas.ctl.benchmark.runner import MasBenchRunner, select_mas_runner
from mas.lab.runners.constants import DEFAULT_LAB_RUNNER_ID


def test_mas_bench_runner_id_is_mas_lab():
    assert MasBenchRunner.runner_id == DEFAULT_LAB_RUNNER_ID
    assert select_mas_runner().runner_id == DEFAULT_LAB_RUNNER_ID
