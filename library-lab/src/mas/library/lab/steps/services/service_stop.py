#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""service_stop — pipeline step that tears down an infrastructure service.

Stops a service that was previously started by :class:`service_start.ServiceStartStep`.
Intended to run in the default ``post`` phase (after all benchmark runs) so
that infrastructure services are kept alive for the duration of the experiment.

Config keys
-----------
service : str (required)
    Name of the service as declared in the infra bundle YAML.
infra : str, default "services"
    Infra bundle name (must match the value used in ``service_start``).

Example (experiment ``pipeline:`` section, phase=post / default):

.. code-block:: yaml

    pipeline:
      - type: service_stop
        name: stop-otel
        depends_on: [export-otel]   # optional, for explicit ordering
        config:
          service: otel-collector
          infra: local-test
"""

import logging
from pathlib import Path
from typing import Any, Optional

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.library.lab.steps.services.service_start import _resolve_infra_yaml

logger = logging.getLogger(__name__)


class ServiceStopStep(PipelineStep):
    """Stop a named service from an infra bundle.

    Delegates to :class:`~mas.lab.benchmark.service_manager.ServiceManager`.
    """

    type = "service_stop"

    def outputs_exist(self, output_dir: Path) -> bool:
        # Service lifecycle steps are always executed — never skipped by cache.
        return False

    async def execute(self, ctx: Any) -> StepOutput:  # type: ignore[override]
        from mas.lab.benchmark.service_manager import ServiceManager

        service_name: str = self.config["service"]
        infra_name: str = self.config.get("infra", "services")

        services_yaml = _resolve_infra_yaml(infra_name, ctx)
        logger.info(
            "service_stop: stopping %r from %s", service_name, services_yaml
        )

        mgr = ServiceManager(services_yaml=services_yaml)
        ok = mgr.stop(service_name)

        if ok:
            logger.info("service_stop: %r stopped", service_name)
        else:
            logger.warning("service_stop: stop returned failure for %r", service_name)

        return StepOutput(
            metadata={
                "service": service_name,
                "stopped": ok,
                "infra": infra_name,
            }
        )
