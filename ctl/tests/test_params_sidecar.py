#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest params reach tools through the agent context only."""

from mas.ctl.session.params_sidecar import apply_runtime_params_to_instance


def test_apply_runtime_params_to_instance() -> None:
    from mas.runtime.driver.instance import RuntimeInstance

    inst = RuntimeInstance.from_parts()
    apply_runtime_params_to_instance({"region": "eu-west-1"}, inst)
    assert inst.driver.ctx.runtime_params == {"region": "eu-west-1"}
