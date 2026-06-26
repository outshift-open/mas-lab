#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tool Contract - External tool execution interface.

Paper Reference: Section 4.2 - "Tool Contract (Invocation + Result)"

The Tool Contract guarantees:
1. Uniform invocation schema across all frameworks
2. Idempotency markers for safe retries
3. Structured result types with error mapping
4. Governance enforcement point (primary checkpoint)

This is the PRIMARY governance boundary where:
- Rate limiters operate
- Authorization checks run
- Cost controls apply
- Tool allowlists enforce

Hook Usage:
- pre_tool_call: Validate, authorize, log BEFORE tool execution
- post_tool_call: Process results, filter, audit AFTER tool execution

Implementations:
- ToolServerPlugin: tool-server protocol tool serving
- LlamaIndexToolsPlugin: LlamaIndex tool integration
- ToolServerBundleServer: ToolBundle manifest → full tool server

Pydantic Input pattern (recommended for new tools)
--------------------------------------------------
Declare a ``class Input(BaseModel)`` inside the tool class.  The runtime
picks it up automatically:

  1. ``get_parameters_schema()``   → JSON Schema derived from ``Input.model_json_schema()``
  2. ``call_tool()``               → ``Input(**arguments)`` validates args before ``execute()``
  3. tool-server ``inputSchema``          → identical JSON Schema served to any tool-server client

Example::

    from pydantic import BaseModel, Field
    from mas.runtime.contracts import ToolContract

    class CheckHealthTool(ToolContract):
        class Input(BaseModel):
            service_name: str = Field(..., description="Service name or URL")
            timeout_seconds: int = Field(5, ge=1, le=300,
                                         description="Max wait time in seconds")

        def get_name(self) -> str:
            return "check-service-health"

        def get_description(self) -> str:
            return (
                "Check the health of a running service. "
                "Returns {healthy: bool, latency_ms: float}."
            )

        def execute(self, **kwargs) -> dict:
            args = self.Input(**kwargs)    # validated; Pydantic raises on bad types
            # ... call actual service ...
            return {"healthy": True, "latency_ms": 42.0}

Legacy API (JSON Schema in get_parameters_schema) continues to work unchanged.
"""

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, create_model

from mas.runtime.contracts.base import CapabilityContract  # L3->L3

logger = logging.getLogger(__name__)


@dataclass
class ToolEvent:
    """Canonical runtime event emitted by a stream or session tool."""

    name: str
    payload: Any = None
    sequence: Optional[int] = None
    timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"name": self.name, "payload": self.payload}
        if self.sequence is not None:
            data["sequence"] = self.sequence
        if self.timestamp is not None:
            data["timestamp"] = self.timestamp
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass
class ToolResultEnvelope:
    """Normalized tool result envelope across inline, stream, and session modes."""

    result_mode: str = "inline"
    execution_mode: str = "sync"
    status: str = "ok"
    result: Any = None
    events: List[ToolEvent] = field(default_factory=list)
    session_id: Optional[str] = None
    session_status: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def inline(cls, result: Any, *, execution_mode: str = "sync") -> "ToolResultEnvelope":
        return cls(result_mode="inline", execution_mode=execution_mode, result=result)

    @classmethod
    def stream(
        cls,
        events: List[ToolEvent],
        *,
        result: Any = None,
        execution_mode: str = "async",
    ) -> "ToolResultEnvelope":
        return cls(
            result_mode="stream",
            execution_mode=execution_mode,
            result=result,
            events=list(events),
        )

    @classmethod
    def session(
        cls,
        session_id: str,
        *,
        events: Optional[List[ToolEvent]] = None,
        result: Any = None,
        execution_mode: str = "realtime",
        session_status: str = "open",
    ) -> "ToolResultEnvelope":
        return cls(
            result_mode="session",
            execution_mode=execution_mode,
            result=result,
            events=list(events or []),
            session_id=session_id,
            session_status=session_status,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "status": self.status,
            "result_mode": self.result_mode,
            "execution_mode": self.execution_mode,
        }
        if self.result is not None:
            data["result"] = self.result
        if self.events:
            data["events"] = [event.to_dict() for event in self.events]
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.session_status is not None:
            data["session_status"] = self.session_status
        if self.metadata:
            data["metadata"] = self.metadata
        return data


def is_tool_event_stream(value: Any) -> bool:
    """Return True when *value* is a generator-like stream of events."""
    if isinstance(value, (str, bytes, dict, ToolEvent, ToolResultEnvelope)):
        return False
    return inspect.isgenerator(value) or inspect.isasyncgen(value)


def coerce_tool_event(value: Any, sequence: Optional[int] = None) -> ToolEvent:
    """Normalize arbitrary event payloads to ``ToolEvent``."""
    if isinstance(value, ToolEvent):
        event = value
    elif isinstance(value, dict) and "name" in value:
        event = ToolEvent(
            name=str(value.get("name", "event")),
            payload=value.get("payload"),
            sequence=value.get("sequence"),
            timestamp=value.get("timestamp"),
            metadata=dict(value.get("metadata") or {}),
        )
    else:
        event = ToolEvent(name="event", payload=value)
    if event.sequence is None and sequence is not None:
        event.sequence = sequence
    return event


# ---------------------------------------------------------------------------
# Argument coercion helpers (used by ToolContract.call_tool)
# ---------------------------------------------------------------------------

def _to_json_str(v: Any) -> str:
    """Coerce any value to a string; dicts/lists become JSON, others use str()."""
    if isinstance(v, str):
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


_JSON_STR = Annotated[str, BeforeValidator(_to_json_str)]

_JSONSCHEMA_TO_PY: Dict[str, Any] = {
    "string":  _JSON_STR,
    "integer": int,
    "number":  float,
    "boolean": bool,
    "array":   list,
    "object":  dict,
}


def _build_args_model(schema: Dict[str, Any]) -> "type[BaseModel] | None":
    """Build a Pydantic model from a JSON Schema *object* spec.

    Returns ``None`` when no ``properties`` are defined (no coercion needed).
    Pydantic will coerce incoming values to the declared types, raising a
    ``ValidationError`` on genuine type mismatches (e.g. list where int expected).
    String fields accept any scalar/dict/list and serialise to JSON.
    """
    props = schema.get("properties")
    if not props:
        return None
    required = set(schema.get("required", []))
    fields: Dict[str, Any] = {}
    for name, spec in props.items():
        py_type = _JSONSCHEMA_TO_PY.get(spec.get("type", ""), Any)
        if name in required:
            fields[name] = (py_type, ...)
        else:
            fields[name] = (Optional[py_type], None)
    return create_model("_ToolArgs", __config__=ConfigDict(extra="allow"), **fields)


class ToolContract(CapabilityContract):

    contract_id = "tool"
    """Base interface for tool execution using hooks.

    Two implementation styles are supported:

    **Style A — Pydantic Input (recommended)**::

        class MyTool(ToolContract):
            class Input(BaseModel):
                param: str = Field(..., description="...")

            def get_name(self) -> str: return "my-tool"
            def get_description(self) -> str: return "..."
            def execute(self, **kwargs) -> dict:
                args = self.Input(**kwargs)   # validated by Pydantic
                ...

    ``get_parameters_schema()`` is auto-derived from ``Input.model_json_schema()``.
    No need to write JSON Schema by hand.

    **Style B — Legacy JSON Schema**::

        class MyTool(ToolContract):
            def get_name(self) -> str: return "my-tool"
            def get_parameters_schema(self) -> dict:
                return {"type": "object", "properties": {"param": {"type": "string"}}}
            def execute(self, **kwargs) -> dict: ...

    For composite providers (multi-tool), override ``list_tools()`` and
    ``call_tool()`` directly.
    """

    # ------------------------------------------------------------------
    # Single-tool helper API (subclasses implementing one tool)
    # ------------------------------------------------------------------

    def get_name(self) -> str:                     # noqa: D401
        raise NotImplementedError(f"{self.__class__.__name__} must implement get_name()")

    def get_description(self) -> str:
        return ""

    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return JSON Schema for the tool's input parameters.

        When the subclass defines ``class Input(BaseModel)``, this default
        implementation auto-derives the schema from
        ``Input.model_json_schema()`` — no need to override.
        Override explicitly only for legacy JSON-Schema-only tools.
        """
        input_cls = getattr(self, "Input", None)
        if input_cls is not None and hasattr(input_cls, "model_json_schema"):
            schema = input_cls.model_json_schema()
            # model_json_schema() may add $defs — strip for LLM clarity
            schema.pop("$defs", None)
            schema.pop("title", None)
            return schema
        return {}

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    def on_collect_tools(self) -> List[Dict[str, Any]]:
        """Hook handler: list tools when requested."""
        return self.list_tools()

    def on_execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Hook handler: execute tool if we own it.
        
        This hook is executed by the runtime when a tool needs to be called.
        It checks if this provider owns the tool, and if so, executes it.
        """
        # Simple check: do we have this tool?
        tools = self.list_tools()
        if any(t["name"] == tool_name for t in tools):
            try:
                # We own this tool, execute it.
                # If call_tool is async, we ideally should await it, but we are in a sync hook.
                # If the runtime supports async hooks, this should be async.
                # Given current runtime is sync, we assume sync execution or compatible return.
                if asyncio.iscoroutinefunction(self.call_tool):
                    # Blocking call for sync runtime compatibility
                    # Warning: This is not ideal for high-performance async runtimes.
                    try:
                        loop = asyncio.get_running_loop()
                        # If we are already in a loop, we return the coroutine and hope the caller handles it?
                        # Or we use a thread?
                        # For now, return coroutine if in loop. 
                        return self.call_tool(tool_name, arguments)
                    except RuntimeError:
                        return asyncio.run(self.call_tool(tool_name, arguments))
                
                return self.call_tool(tool_name, arguments)
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "tool": tool_name
                }
        return None

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool with given arguments.
        
        Default implementation: delegates to execute(**arguments) when
        the tool name matches get_name(). Subclasses may override for
        composite providers or custom dispatch.
        """
        try:
            own = self.get_name()
        except NotImplementedError:
            own = None

        if own and tool_name == own:
            # Coerce arguments against the declared JSON Schema so that the LLM
            # sending e.g. a dict for a `string` field is handled gracefully.
            try:
                _schema = self.get_parameters_schema()
            except (NotImplementedError, AttributeError):
                _schema = {}
            _model = _build_args_model(_schema)
            if _model:
                _validated = _model.model_validate(arguments)
                arguments = _validated.model_dump(exclude_unset=True)
            return self.execute(**arguments)

        raise NotImplementedError(
            f"{self.__class__.__name__} must implement call_tool(). "
            "This method is invoked within the hook pipeline after pre_tool_call passes."
        )
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools with metadata.

        Default implementation: builds a single-entry list from get_name(),
        get_description(), and get_parameters_schema() when defined.
        Subclasses may override for composite providers.
        """
        try:
            name = self.get_name()
        except NotImplementedError:
            raise NotImplementedError(
                f"{self.__class__.__name__} must implement list_tools()"
            )
        try:
            desc = self.get_description()
        except (NotImplementedError, AttributeError):
            desc = ""
        try:
            params = self.get_parameters_schema()
        except (NotImplementedError, AttributeError):
            params = {}
        return [{"name": name, "description": desc, "parameters": params}]

    def to_tool_spec(self) -> Dict[str, Any]:
        """Return the tool-server-compatible tool spec dict.

        Convenience wrapper around ``list_tools()[0]``, structured as the
        tool-server ``/tools/list`` entry:
        ``{"name": ..., "description": ..., "inputSchema": ...}``.
        """
        tools = self.list_tools()
        if not tools:
            raise ValueError(f"{self.__class__.__name__}.list_tools() returned empty list")
        t = tools[0]
        return {
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "inputSchema": t.get("parameters", {}),
        }

    def get_execution_mode(self, tool_name: Optional[str] = None) -> str:
        """Return the declared execution mode for a tool when available."""
        specs = self.list_tools()
        if tool_name is not None:
            for spec in specs:
                if spec.get("name") == tool_name:
                    return str(spec.get("execution_mode") or "sync")
        return "sync"

    def get_result_mode(self, tool_name: Optional[str] = None) -> str:
        """Return the declared result mode for a tool when available."""
        specs = self.list_tools()
        if tool_name is not None:
            for spec in specs:
                if spec.get("name") == tool_name:
                    return str(spec.get("result_mode") or "inline")
        return "inline"
    
    # Hook Implementations for Runtime Integration
    
    def on_collect_tools(self, **kwargs) -> List[Dict[str, Any]]:
        """Hook: Collect tools from this plugin."""
        return self.list_tools()

    def on_execute_tool(self, tool_name: str, arguments: Dict[str, Any], **kwargs) -> Dict[str, Any] | None:
        """Hook: Execute tool if this plugin owns it."""
        # Check if we own this tool
        is_supported = False
        try:
            tools = self.list_tools()
            for t in tools:
                if t.get("name") == tool_name:
                    is_supported = True
                    break
        except Exception:
            # If we can't list tools, we probably can't execute either.
            logger.warning(
                "Tool support check failed for %r; treating as unsupported.",
                tool_name,
                exc_info=True,
            )

        if is_supported:
            # We handle this tool. Let execution exceptions propagate.
            # This ensures execute_first_result stops here (if we fix execute_first_result).
            return self.call_tool(tool_name, arguments)
            
        return None


    # Hook methods (optional overrides for governance)
    
    def pre_tool_call(self, context: Dict[str, Any]) -> Dict[str, Any]:

        """Hook called BEFORE tool execution.
        
        Override this to implement:
        - Authorization checks (is tool allowed?)
        - Rate limiting (quota exceeded?)
        - Cost tracking (log estimated cost)
        - Input validation (sanitize arguments)
        
        Args:
            context: {
                "tool_name": str,
                "arguments": dict,
                "agent_id": str,
                "session_id": str,
            }
        
        Returns:
            Modified context (or raise exception to block)
        """
        return context
    
    def post_tool_call(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Hook called AFTER tool execution.
        
        Override this to implement:
        - Result filtering (redact sensitive data)
        - Quality scoring (evaluate tool output)
        - Retry logic (on transient failures)
        - Audit logging (record execution details)
        
        Args:
            context: {
                "tool_name": str,
                "arguments": dict,
                "result": dict,
                "execution_time_ms": float,
                "agent_id": str,
            }
        
        Returns:
            Modified context with potentially modified result
        """
        return context
