#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""SessionObservabilityRecorder — lifecycle handle for a session's obs plugin set."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mas.runtime.boundary.obs.plugins import ObsPluginSet


@dataclass
class SessionObservabilityRecorder:
    """Lifecycle handle for a session's obs plugin set. Recording is done by the runtime."""
    plugin_set: "ObsPluginSet | None" = None
    owns_plugin_set: bool = True

    @property
    def owns_pipeline(self) -> bool:
        """Backward-compat alias for owns_plugin_set."""
        return self.owns_plugin_set

    def close(self) -> None:
        if self.plugin_set is not None and self.owns_plugin_set:
            self.plugin_set.flush()
            self.plugin_set.close()

    def flush(self) -> None:
        if self.plugin_set is not None:
            self.plugin_set.flush()
