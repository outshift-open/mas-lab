"""SRE tool: get_service_health — returns overall health status of a service.

Scenario-aware: service health is loaded from the active incident fixture via
``_scene.py``.  Select the active incident declaratively via
``spec.params.incident_fixture:`` in the active overlay.

When called with a service not in the incident fixture, returns plausible
nominal health data (status=healthy, no dependency failures).
"""

from typing import Any, Dict, List

from pathlib import Path

from mas.runtime.contracts import ToolContract
from ._scene import IncidentScene, NominalServiceScene, _resolve_fixture_path


class GetServiceHealthTool(ToolContract):
    """Check the health status of a service and its dependencies."""

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
                "name": "get_service_health",
                "description": (
                    "Check the health status of a service. "
                    "Returns overall status (healthy/degraded/critical), uptime, "
                    "and the health of each dependency."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name to check",
                        },
                        "include_dependencies": {
                            "type": "boolean",
                            "description": "Whether to include dependency health (default: true)",
                        },
                    },
                    "required": ["service"],
                },
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "get_service_health":
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
        include_deps = arguments.get("include_dependencies", True)

        # --- Scene-aware branch ---
        svc_key = self.scene.match(service)
        if svc_key:
            health = self.scene.services[svc_key].health
            result = {"service": service, **health}
            if not include_deps:
                result.pop("dependencies", None)
            return result

        # --- Service not in fixture: return plausible nominal data ---
        health = NominalServiceScene(service).health
        result = {"service": service, **health}
        if not include_deps:
            result.pop("dependencies", None)
        return result

    # ------------------------------------------------------------------
    # Legacy interface delegators
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by GetServiceHealthTool")
        return result
