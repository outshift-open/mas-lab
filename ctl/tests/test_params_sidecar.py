#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Params sidecar for tool fixture resolution."""

from pathlib import Path

from mas.ctl.session.params_sidecar import (
    MAS_RUNTIME_ARTIFACTS_ENV,
    apply_runtime_params_to_instance,
    stage_runtime_params,
)


def test_stage_runtime_params_uses_runtime_dir(tmp_path: Path) -> None:
    env = {"XDG_RUNTIME_DIR": str(tmp_path)}
    path = stage_runtime_params(
        {"incident_fixture": "datasets/incidents/payment-async-timeout.yaml"},
        environ=env,
    )
    assert path is not None
    assert path.name == "scene.yaml"
    text = path.read_text(encoding="utf-8")
    assert "incident_fixture" in text
    assert "payment-async-timeout" in text
    root = Path(env[MAS_RUNTIME_ARTIFACTS_ENV])
    assert path.is_relative_to(root)


def test_apply_runtime_params_to_instance() -> None:
    from mas.runtime.driver.instance import RuntimeInstance

    inst = RuntimeInstance.from_parts()
    apply_runtime_params_to_instance({"incident_fixture": "x.yaml"}, inst)
    assert inst.driver.ctx.runtime_params == {"incident_fixture": "x.yaml"}
