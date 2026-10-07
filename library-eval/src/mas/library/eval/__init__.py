#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.library.eval — output quality evaluators and MCE pipeline steps."""

from pathlib import Path

from mas.library.eval.evaluator import (
    DEFAULT_METRIC_PROVIDER,
    EvalProvider,
    MetricScore,
    evaluate_run,
    get_provider,
    list_available_providers,
    list_metrics,
    register_provider,
)


def package_root() -> Path:
    """Return the directory containing ``library.yaml`` for this manifest library."""
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "library.yaml").is_file():
            return parent
    return here


__all__ = [
    "DEFAULT_METRIC_PROVIDER",
    "EvalProvider",
    "MetricScore",
    "evaluate_run",
    "get_provider",
    "list_available_providers",
    "list_metrics",
    "package_root",
    "register_provider",
]
