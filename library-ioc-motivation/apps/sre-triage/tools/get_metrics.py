"""SRE tool: get_metrics — returns mock service performance metrics.

Scenario-aware: service data is loaded from the active incident fixture via
``_scene.py``.  The active fixture is selected declaratively using
``spec.params.incident_fixture:`` in the active overlay.

When called with a service not in the incident fixture, returns plausible
nominal (healthy) metrics for that service.  This is intentional: an explicit
error response would guide agents back to the correct service name, defeating
fault-injection experiments that redirect agents to investigate the wrong
service.
"""

from typing import Any, Dict, List

from pathlib import Path

from mas.runtime.contracts import ToolContract
from ._scene import IncidentScene, NominalServiceScene, _resolve_fixture_path


class GetMetricsTool(ToolContract):
    """Retrieve current performance metrics for a service.

    Supports an optional ``metric`` parameter to fetch a named metric
    (e.g. ``lock_wait_count``, ``deadlock_count``, ``active_connections``)
    instead of the generic latency bundle.
    """

    def __init__(self, fixture_path: str | None = None) -> None:
        self._fixture_path = fixture_path
        self._scene: IncidentScene | None = None

    @property
    def scene(self) -> IncidentScene:
        if self._scene is None:
            path = Path(self._fixture_path) if self._fixture_path else _resolve_fixture_path()
            self._scene = IncidentScene(path)
        return self._scene

    def on_collect_tools(self, **_: Any) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_metrics",
                "description": (
                    "Retrieve current performance metrics for a given service. "
                    "Returns latency (p50/p95/p99), error rate, and request throughput. "
                    "Use the optional 'metric' parameter to fetch a specific named metric "
                    "such as 'lock_wait_count', 'deadlock_count', or 'active_connections'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name (e.g. 'payment-service', 'payment_db')",
                        },
                        "window": {
                            "type": "string",
                            "enum": ["1m", "5m", "15m", "1h"],
                            "description": "Aggregation window (default: 5m)",
                        },
                        "metric": {
                            "type": "string",
                            "description": (
                                "Optional: name of a specific metric to retrieve. "
                                "Supported for DB services: 'lock_wait_count', 'deadlock_count', "
                                "'active_connections', 'query_latency_p99', 'replication_lag_ms', "
                                "'cache_hit_ratio'."
                            ),
                        },
                    },
                    "required": ["service"],
                },
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "get_metrics":
            return None
        # Accept both 'service' (schema) and 'service_name' (LLM natural preference)
        service = arguments.get("service") or arguments.get("service_name")
        if not service:
            return {
                "error": "required parameter 'service' is missing",
                "hint": (
                    "Specify the target service name, e.g. service='payment-service'. "
                    f"Services available in this incident: {sorted(self.scene.services.keys())}"
                ),
            }
        window = arguments.get("window", "5m")
        metric = arguments.get("metric")

        # --- Scene-aware branch ---
        svc_key = self.scene.match(service)
        if svc_key:
            svc = self.scene.services[svc_key]
            if metric:
                named = svc.named_metric(metric)
                if named is not None:
                    return {"service": service, "window": window, "metric": metric, **named}
            metrics = svc.metrics
            # expose named metrics in the flat response for DB-like services
            named_all = metrics.pop("named", None)
            result = {"service": service, "window": window, **metrics}
            if named_all:
                result["named_metrics"] = named_all
            return result

        # --- Service not in fixture: return plausible nominal data ---
        # Do NOT return an error here. An error with available_services hints
        # would guide agents back to the correct service, defeating fault
        # injection that redirects investigation to the wrong service.
        svc = NominalServiceScene(service)
        if metric:
            named = svc.named_metric(metric)
            if named is not None:
                return {"service": service, "window": window, "metric": metric, **named}
        metrics = svc.metrics
        return {"service": service, "window": window, **metrics}

    # ------------------------------------------------------------------
    # Legacy interface delegators
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by GetMetricsTool")
        return result
