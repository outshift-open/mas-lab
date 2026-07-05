#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# Removed — ObservabilityConfig moved to config.py; ObservabilityPipeline replaced by
# mas.runtime.boundary.obs.loader.ObsPluginSet.
# This shim keeps legacy imports from exploding during the transition.
from mas.ctl.adapters.obs.config import ObservabilityConfig  # noqa: F401

__all__ = ["ObservabilityConfig"]
