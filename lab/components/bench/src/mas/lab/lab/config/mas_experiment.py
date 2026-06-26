#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from mas.lab.manifests import load_experiment_data

from .execution import MASExecutionSpec
from .experiment_base import MASRunBase

@dataclass
class MASExperimentConfig(MASRunBase):
    """Batch experiment configuration for running a MAS across scenarios."""

    execution: MASExecutionSpec = field(default_factory=MASExecutionSpec)
    """Batch execution parameters."""

    default_flavour: Optional[str] = "local"
    """Default flavour name (library-standard)."""

    default_infra: Optional[str] = None
    """Default infra bundle name for service/codec pipeline steps."""

    @classmethod
    def from_yaml(cls, path: Path) -> "MASExperimentConfig":
        """Load a MASExperimentConfig from an experiment YAML file."""
        data, _manifest_version = load_experiment_data(path)

        exp_data = data.get("experiment", data)
        base_dir = path.parent

        if "applications" not in exp_data:
            raise ValueError(
                f"{path}: experiment must declare applications: [{{manifest|app, configs_dir}}]"
            )

        base = cls._load_base_fields(exp_data, base_dir, yaml_path=path)

        execution = MASExecutionSpec.from_dict(exp_data.get("execution", {}))
        run_level = base.get("levels", {}).get("run")
        if run_level is not None and run_level.n_runs is not None:
            execution.n_runs = run_level.n_runs

        default_flavour = exp_data.get("default_flavour") or "local"
        default_infra = exp_data.get("default_infra") or None

        config = cls(
            **base,
            execution=execution,
            default_flavour=default_flavour,
            default_infra=default_infra,
        )
        config._path = path
        return config
