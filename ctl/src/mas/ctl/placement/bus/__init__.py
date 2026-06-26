#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Communication bus — inter-agent transport outside the Mealy kernel."""

from mas.ctl.placement.bus.inproc import InProcessCommBus
from mas.ctl.placement.bus.protocol import CommBus, CommEndpoint

__all__ = ["CommBus", "CommEndpoint", "InProcessCommBus"]
