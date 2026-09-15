"""SRE tool: list_services — enumerates all services known to the active incident fixture.

Scenario-aware: the service catalogue is loaded from the active incident fixture
via ``_scene.py``.  Select the active incident declaratively via
``spec.params.incident_fixture:`` in the active overlay.

Returns the canonical name and health status of every service in the scene.
Useful as a first step when the agent does not yet know which services are
involved in the incident.
"""

from typing import Any, Dict, List
from pathlib import Path

from mas.runtime.contracts import ToolContract
from ._scene import IncidentScene, _resolve_fixture_path


class ListServicesTool(ToolContract):
    """List all services tracked in the active incident fixture."""

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
                "name": "list_services",
                "description": (
                    "List all services in the current incident scope. "
                    "Returns each service's canonical name, health status, "
                    "and a brief summary. Use this as a first step to discover "
                    "which services are involved before drilling into metrics or logs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_health": {
                            "type": "boolean",
                            "description": (
                                "When true (default), include the health status "
                                "(healthy/degraded/critical) for each service."
                            ),
                        },
                    },
                    "required": [],
                },
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "list_services":
            return None

        include_health = arguments.get("include_health", True)

        services = []
        for key, svc in self.scene.services.items():
            entry: Dict[str, Any] = {"name": key}
            if svc._data.get("aliases"):
                entry["aliases"] = svc._data["aliases"]
            if include_health:
                health = svc.health
                entry["status"] = health.get("status", "unknown")
                note = health.get("note") or svc._data.get("metrics", {}).get("note")
                if note:
                    # Trim to one sentence for brevity
                    first_sentence = note.strip().split("\n")[0].rstrip(".")
                    entry["summary"] = first_sentence
            services.append(entry)

        return {
            "service_count": len(services),
            "services": services,
        }

    # ------------------------------------------------------------------
    # Legacy interface delegators
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by ListServicesTool")
        return result
