#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Versioned manifest loader.

Loads experiment and pipeline YAML, validates the declared format version, and
returns the parsed document. Only the current format version is supported in this
release.
"""

from pathlib import Path
from typing import Any, Dict, Tuple

from mas.lab.manifests.versions import assert_supported, detect_version
from mas.runtime.spec.source import load_yaml_file


def load_experiment_data(path: Path) -> Tuple[Dict[str, Any], str]:
    """Parse an experiment YAML file."""
    raw = _read_yaml(path)
    version = detect_version(raw)
    assert_supported(version, path)
    return raw, version


def load_pipeline_data(path: Path) -> Tuple[Dict[str, Any], str]:
    """Parse a pipeline YAML file."""
    raw = _read_yaml(path)
    version = detect_version(raw)
    assert_supported(version, path)
    return raw, version


def normalize_manifest_version(
    raw: Dict[str, Any],
    manifest_type: str,
    path: Path,
) -> Tuple[Dict[str, Any], str]:
    """Detect manifest version for pre-loaded YAML data."""
    version = detect_version(raw)
    assert_supported(version, path)
    return raw, version


def _read_yaml(path: Path) -> Dict[str, Any]:
    raw = load_yaml_file(path)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: manifest must be a YAML mapping")
    return raw
