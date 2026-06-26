#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""RuntimeBuilder embed smoke tests."""

from mas.runtime.factory.builder import RuntimeBuilder
from mas.runtime.kernel.config import KernelConfig


def test_runtime_builder_produces_instance():
    instance = RuntimeBuilder(config=KernelConfig()).build()
    assert instance.driver is not None


def test_runtime_builder_from_config():
    from mas.runtime.factory.builder import RuntimeBuilder

    instance = RuntimeBuilder.from_config(KernelConfig())
    assert instance.driver is not None
