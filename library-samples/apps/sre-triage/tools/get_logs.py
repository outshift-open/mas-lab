"""SRE tool: get_logs — returns recent log entries for a service.

Scenario-aware: service logs are loaded from the active incident fixture via
``_scene.py``.  Select the active incident declaratively via
``spec.params.incident_fixture:`` in the active overlay.

When called with a service not in the incident fixture, returns plausible
nominal INFO-level log entries (no errors, no anomalies).
"""

from typing import Any, Dict, List

from pathlib import Path

from mas.runtime.contracts import ToolContract
from ._scene import IncidentScene, NominalServiceScene, _resolve_fixture_path

class GetLogsTool(ToolContract):
    """Retrieve recent log entries for a service."""

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
                "name": "get_logs",
                "description": (
                    "Retrieve recent log entries for a service. "
                    "Supports filtering by severity level and limiting the number of entries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name to fetch logs for",
                        },
                        "level": {
                            "type": "string",
                            "enum": ["DEBUG", "INFO", "WARN", "ERROR"],
                            "description": "Minimum log level filter (default: INFO)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of entries to return (default: 10, max: 50)",
                        },
                    },
                    "required": ["service"],
                },
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "get_logs":
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
        level_filter = arguments.get("level", "INFO")
        limit = min(int(arguments.get("limit", 10)), 50)

        # --- Scene-aware branch ---
        svc_key = self.scene.match(service)
        if svc_key:
            svc = self.scene.services[svc_key]
            _levels = ["DEBUG", "INFO", "WARN", "ERROR"]
            min_idx = _levels.index(level_filter) if level_filter in _levels else 1
            filtered = [
                e for e in svc.logs
                if _levels.index(e["level"]) >= min_idx
            ][:limit]
            return {"service": service, "entries": filtered, "total": len(filtered)}

        # --- Service not in fixture: return plausible nominal data ---
        svc = NominalServiceScene(service)
        entries = svc.logs[:limit]
        return {"service": service, "entries": entries, "total": len(entries)}

    # ------------------------------------------------------------------
    # Legacy interface delegators
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by GetLogsTool")
        return result
