"""SRE tool: get_deployments — returns recent deployment history for a service.

Scenario-aware: deployment data is loaded from the active incident fixture via
``_scene.py``.  Select the active incident declaratively via
``spec.params.incident_fixture:`` in the active overlay.

When called with a service not in the incident fixture, returns plausible
nominal deployment history (no incident-correlated deployment).
"""

from typing import Any, Dict, List

from pathlib import Path

from mas.runtime.contracts import ToolContract
from ._scene import IncidentScene, NominalServiceScene, _resolve_fixture_path


class GetDeploymentsTool(ToolContract):
    """Retrieve recent deployment history for a service."""

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
                "name": "get_deployments",
                "description": (
                    "Retrieve the deployment history for a service. "
                    "Returns a list of recent releases with version, SHA, commit message, "
                    "timestamp, status, and whether the deploy overlaps with the incident window."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name to look up",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of most recent deployments to return (default: 5)",
                        },
                        "window": {
                            "type": "string",
                            "description": "Optional time window filter e.g. '60m', '24h'",
                        },
                    },
                    "required": ["service"],
                },
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "get_deployments":
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
        limit = min(int(arguments.get("limit", 5)), 20)

        # --- Scene-aware branch ---
        svc_key = self.scene.match(service)
        if svc_key:
            deploys = self.scene.services[svc_key].deployments[:limit]
            return {
                "service": service,
                "deployments": deploys,
                "incident_correlations": [
                    d for d in deploys if d.get("overlap_with_incident")
                ],
            }

        # --- Service not in fixture: return plausible nominal data ---
        svc = NominalServiceScene(service)
        deploys = svc.deployments[:limit]
        return {
            "service": service,
            "deployments": deploys,
            "incident_correlations": [],
        }

    # ------------------------------------------------------------------
    # Legacy interface delegators
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by GetDeploymentsTool")
        return result
