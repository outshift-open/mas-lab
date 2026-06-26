#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Packaging-hygiene guards.

These tests lock in fixes that are otherwise easy to silently regress:

* No local run output may live inside packaged source (it would ship to PyPI).
* The umbrella ``mas-lab`` wheel must not re-ship modules owned by its
  components (``benchmark/`` -> mas-lab-bench, ``telemetry/`` -> mas-lab-core),
  which would create install-order-dependent file collisions.
* All ``mas`` / ``mas.lab`` namespace contributions must use PEP 420 implicit
  namespaces consistently (no stray ``__init__.py`` namespace markers), so
  components do not shadow each other.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Every package src tree that installs into the shared ``mas`` namespace.
NAMESPACE_PACKAGE_SRCS = [
    "lab/src",
    "lab/components/core/src",
    "lab/components/bench/src",
    "lab/components/controller/src",
    "lab/components/content/src",
]


def test_no_run_output_inside_packaged_source():
    output_dir = REPO_ROOT / "lab/src/mas/lab/output"
    assert not output_dir.exists(), (
        "Run output found inside packaged source; it would ship in the wheel. "
        "Remove lab/src/mas/lab/output and keep it gitignored."
    )


def test_umbrella_does_not_reship_component_modules():
    umbrella = REPO_ROOT / "lab/src/mas/lab"
    for owned in ("benchmark", "telemetry"):
        assert not (umbrella / owned).exists(), (
            f"lab/src/mas/lab/{owned} is owned by a component package; the umbrella "
            "must not also ship it (file collision on install)."
        )


def test_namespace_packages_use_pep420_consistently():
    """No package may ship mas/__init__.py or mas/lab/__init__.py."""
    offenders = []
    for src in NAMESPACE_PACKAGE_SRCS:
        for marker in ("mas/__init__.py", "mas/lab/__init__.py"):
            if (REPO_ROOT / src / marker).exists():
                offenders.append(f"{src}/{marker}")
    assert not offenders, (
        "These namespace markers break PEP 420 consistency and can shadow "
        f"sibling packages: {offenders}"
    )
