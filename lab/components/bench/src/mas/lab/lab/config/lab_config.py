#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mas.lab.manifests import load_experiment_data

from .experiment_base import MASRunBase
from .ui import UISpec

@dataclass
class LabConfig(MASRunBase):
    """Lab configuration — interactive execution of a MAS across named scenarios.

    Loaded from a ``lab-config.yaml`` file.  Adds ``ui: UISpec`` on top of the shared
    ``MASRunBase`` fields (port, layout, node positions for the topology view).

    What LabConfig does NOT have (vs MASExperimentConfig):
    * ``flavours``  — demo always runs in "local" mode
    * ``execution`` — one run at a time, driven by the UI
    * ``plots``     — replaced by the live UI visualisation
    """

    ui: UISpec = field(default_factory=UISpec)
    """Demo-specific UI hints: port, mode, layout, per-agent node positions."""

    default_flavour: Optional[str] = None
    """Optional runtime flavour name for interactive demo execution."""

    @classmethod
    def from_yaml(cls, path: Path) -> "LabConfig":
        """Load a LabConfig from a ``lab-config.yaml`` file.

        Supports both ``lab:`` as the top-level key and a bare dict (no prefix).
        Loaded from a ``lab-config.yaml`` file path (canonical filename).
        """
        data, _manifest_version = load_experiment_data(path)

        lab_data = data.get("lab", data)
        base_dir = path.parent

        base = cls._load_base_fields(lab_data, base_dir, yaml_path=path)
        ui = UISpec.from_dict(lab_data.get("ui", {}))

        config = cls(**base, ui=ui, default_flavour=lab_data.get("default_flavour"))
        config._path = path
        return config

