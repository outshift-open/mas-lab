#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# Removed — replaced by TransformContext in mas.library.standard.lib.observability.native.transform.
# Shim keeps old imports working.
from __future__ import annotations
from typing import Protocol

class ObservabilityContext(Protocol):
    agent_id: str
    run_id: str
    turn_id: str
    mas_call_id: str
    exec_call_id: str

ObsContext = ObservabilityContext
__all__ = ["ObsContext", "ObservabilityContext"]
