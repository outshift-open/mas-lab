#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Public MCE v1 provider plugin entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional


class MCEv1Provider:
    """Delegates to mas.library.eval MCE v1 provider."""

    name = "mcev1"

    def __init__(self) -> None:
        from mas.library.eval.evaluator import get_provider

        self._delegate = get_provider("mce_v1")

    def compute(
        self,
        kg_path: Path,
        metric_names: List[str],
        *,
        response_agent_id: Optional[str] = None,
    ) -> Dict[str, dict]:
        return self._delegate.compute(
            kg_path=kg_path,
            metric_names=metric_names,
            response_agent_id=response_agent_id,
        )

    def available_metrics(self) -> List[str]:
        return self._delegate.available_metrics()
