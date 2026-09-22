"""SRE tool: run_action — executes a remediation action on a service.

Scenario-aware: rollback results are loaded from the active incident fixture
via ``_scene.py``.  Select the active incident declaratively via
``spec.params.incident_fixture:`` in the active overlay.
"""

from typing import Any, Dict, List

from pathlib import Path

from mas.runtime.contracts import ToolContract
from ._scene import IncidentScene, _resolve_fixture_path

_KNOWN_ACTIONS = {
    "restart": "Service restart initiated. Expected recovery: ~30s.",
    "scale_up": "Scaling up service by 2 additional replicas.",
    "scale_down": "Scaling down service by 1 replica.",
    "rollback": "Rollback to previous version triggered.",
    "clear_cache": "Cache flush initiated for service.",
    "toggle_circuit_breaker": "Circuit breaker state toggled.",
    "drain_traffic": "Traffic draining initiated — redirecting to healthy instances.",
    "enable_debug_logging": "Debug-level logging enabled (TTL: 15m).",
    "run_health_check": "Manual health check probe sent.",
    "notify_on_call": "On-call notification dispatched via PagerDuty.",
}


class RunActionTool(ToolContract):
    """Execute a remediation or operational action on a service."""

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
                "name": "run_action",
                "description": (
                    "Execute an operational or remediation action on a service. "
                    "Supported actions: restart, scale_up, scale_down, rollback, clear_cache, "
                    "toggle_circuit_breaker, drain_traffic, enable_debug_logging, "
                    "run_health_check, notify_on_call."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Target service name",
                        },
                        "action": {
                            "type": "string",
                            "enum": list(_KNOWN_ACTIONS.keys()),
                            "description": "Action to execute",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief explanation of why this action is being taken (optional)",
                        },
                    },
                    "required": ["service", "action"],
                },
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "run_action":
            return None
        # Accept both 'service' (schema) and 'service_name' (LLM natural preference)
        service = arguments.get("service") or arguments.get("service_name", "unknown-service")
        action = arguments.get("action", "")
        reason = arguments.get("reason", "")

        message = _KNOWN_ACTIONS.get(action)
        if message is None:
            return {
                "status": "error",
                "service": service,
                "action": action,
                "message": f"Unknown action '{action}'. Supported: {', '.join(_KNOWN_ACTIONS)}",
            }

        # Scenario-aware rollback
        svc_key = self.scene.match(service)
        if action == "rollback" and svc_key:
            rollback = self.scene.services[svc_key].rollback
            if rollback:
                success = self.scene.services[svc_key].do_rollback()
                if success:
                    return {
                        "status": "ok",
                        "service": service,
                        "action": "rollback",
                        **rollback,
                    }
                else:
                    return {
                        "status": "error",
                        "service": service,
                        "action": "rollback",
                        "message": f"Rollback already performed for service '{service}'",
                    }
        return {
            "status": "ok",
            "service": service,
            "action": action,
            "message": message,
            "reason": reason or "not specified",
        }

    # ------------------------------------------------------------------
    # Legacy interface delegators
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by RunActionTool")
        return result
