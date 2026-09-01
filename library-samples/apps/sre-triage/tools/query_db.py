"""SRE tool: query_db — exposes pg_stat_activity-style data for a database service.

Scenario-aware: DB diagnostic data is loaded from the active incident fixture
via ``_scene.py``.  Select the active incident declaratively via
``spec.params.incident_fixture:`` in the active overlay.

For ``payment_db`` in the default incident the DB is clean (no blocking,
no deadlocks), confirming it is *not* the root cause.
"""

from typing import Any, Dict, List

from pathlib import Path

from mas.runtime.contracts import ToolContract
from ._scene import IncidentScene, NominalServiceScene, _resolve_fixture_path


class QueryDbTool(ToolContract):
    """Query database internals (pg_stat_activity, blocking, deadlocks, connection pool)."""

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
                "name": "query_db",
                "description": (
                    "Query database internal statistics similar to pg_stat_activity. "
                    "Use to detect blocking queries, deadlocks, long-running transactions, "
                    "and connection pool exhaustion. "
                    "query_type options: pg_stat_activity, blocking_queries, deadlocks, connection_pool."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Database service name to query",
                        },
                        "query_type": {
                            "type": "string",
                            "enum": [
                                "pg_stat_activity",
                                "blocking_queries",
                                "deadlocks",
                                "connection_pool",
                            ],
                            "description": "Type of database diagnostic to run (default: pg_stat_activity)",
                        },
                    },
                    "required": ["service"],
                },
            }
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any] | None:
        if tool_name != "query_db":
            return None
        # Accept both 'service' (schema) and 'service_name' (LLM natural preference)
        service = arguments.get("service") or arguments.get("service_name")
        if not service:
            return {
                "error": "required parameter 'service' is missing",
                "hint": (
                    "Specify the database service name, e.g. service='payment_db'. "
                    f"Services available in this incident: {sorted(self.scene.services.keys())}"
                ),
            }
        query_type = arguments.get("query_type", "pg_stat_activity")

        # --- Scene-aware branch ---
        svc_key = self.scene.match(service)
        if svc_key:
            svc = self.scene.services[svc_key]
            if query_type in ("blocking_queries", "deadlocks"):
                return {"service": service, "query_type": query_type, **svc.blocking}
            if query_type == "connection_pool":
                return {"service": service, "query_type": query_type, **svc.connection_pool}
            return {"service": service, "query_type": query_type, **svc.pg_stat_activity}

        # --- Service not in fixture: return nominal healthy DB data ---
        return {"service": service, "query_type": query_type,
                **NominalServiceScene(service).query_db(query_type)}

    # ------------------------------------------------------------------
    # Legacy interface delegators
    # ------------------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.on_collect_tools()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.on_execute_tool(tool_name, arguments)
        if result is None:
            raise ValueError(f"Tool '{tool_name}' not handled by QueryDbTool")
        return result
