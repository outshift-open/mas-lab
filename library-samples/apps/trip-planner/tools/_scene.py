#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Dataset helper for the trip-planner tools.

The framework does not expose a dedicated "scene" primitive. Trip planner only
needs a deterministic way to resolve its dataset fixture. That responsibility
stays local to the example and is configured explicitly through tool init params.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_DEFAULT_DATASET = "fixtures/arborian-network.yaml"


def _find_example_root() -> Path:
    """Walk up from this file to find the trip-planner example root."""
    here = Path(__file__).resolve().parent
    # tools/ is one level below the example root
    return here.parent


def resolve_dataset_path(dataset_path: str | None = None) -> Path:
    """Resolve a dataset path relative to the trip-planner example root."""
    root = _find_example_root()
    candidate = Path(dataset_path) if dataset_path else Path(_DEFAULT_DATASET)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


@lru_cache(maxsize=8)
def load_network(dataset_path: str | None = None) -> Dict[str, Any]:
    """Return a parsed dataset fixture.

    The cache key is the declared dataset path so tools using different datasets
    during tests or experiments do not interfere with one another.
    """
    path = resolve_dataset_path(dataset_path)
    with path.open() as f:
        data: Optional[Dict[str, Any]] = yaml.safe_load(f)
    return data or {}


def find_route(network: Dict[str, Any], origin: str, destination: str,
               mode: str = "any") -> list[Dict[str, Any]]:
    """Return all direct routes matching origin, destination, and optional mode."""
    routes = network.get("routes", [])
    result: list[Dict[str, Any]] = []
    for r in routes:
        origin_match = (r.get("from", "").lower() == origin.lower() or
                        r.get("to", "").lower() == origin.lower())
        dest_match = (r.get("to", "").lower() == destination.lower() or
                      r.get("from", "").lower() == destination.lower())
        if not (origin_match and dest_match):
            continue
        if mode != "any" and r.get("mode", "").lower() != mode.lower():
            continue
        result.append(r)
    return result


def find_city(network: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """Return the city record matching *name* (case-insensitive)."""
    for city in network.get("cities", []):
        if city.get("name", "").lower() == name.lower():
            return city
    return None
