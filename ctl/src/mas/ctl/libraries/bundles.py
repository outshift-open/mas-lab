#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest library bundle discovery — same entry-point group as mas-lab v1."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from importlib import metadata
from importlib.resources import as_file, files
from pathlib import Path

import yaml


@dataclass
class BundleInfo:
    library: str
    package: str
    ref: str
    path: str
    kind: str = ""
    name: str = ""


def list_manifest_libraries() -> dict[str, str]:
    try:
        eps = metadata.entry_points(group="mas.runtime.manifest_libraries")
    except Exception:
        return {}
    return {ep.name: ep.value for ep in eps}


def list_bundles(*, verbose: bool = False) -> list[BundleInfo]:
    out: list[BundleInfo] = []
    for lib_name, pkg_name in sorted(list_manifest_libraries().items()):
        try:
            libs_path = files(pkg_name) / "libs" / lib_name
            with as_file(libs_path) as p:
                root = Path(p)
                if not root.is_dir():
                    continue
                for yaml_file in sorted(root.rglob("*.yaml")):
                    rel = yaml_file.relative_to(root)
                    bundle_name = str(rel).replace(".yaml", "").replace("/", ":")
                    ref = f"{lib_name}:{bundle_name}"
                    kind = ""
                    display = bundle_name
                    with contextlib.suppress(Exception):
                        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            kind = str(data.get("kind", ""))
                            display = data.get("metadata", {}).get("name", display)
                    out.append(
                        BundleInfo(
                            library=lib_name,
                            package=pkg_name,
                            ref=ref,
                            path=str(yaml_file),
                            kind=kind,
                            name=str(display),
                        )
                    )
                    if verbose:
                        pass
        except Exception:
            continue
    return out
