"""Schema for ``kind: Tool`` manifests (``apiVersion: mas/v1``).

A ``kind: Tool`` manifest is the declarative contract of a **single tool**:

- ``spec.parameters[]``  — semantic interface (name, type, description, examples)
- ``spec.returns``       — output description
- ``spec.impl``          — implementation details (module_path, class_name, kind)

The split is intentional: the semantic interface is **everything an LLM or
caller needs to invoke the tool correctly**, while the implementation section
is the runtime's concern and is never exposed to callers.

Relation to other manifests
---------------------------
``kind: ToolBundle``  →  index of named ``ToolEntry`` objects (shared registry).
``kind: Tool``        →  standalone contract for a **single** tool.

An agent manifest references tools via ``tools[].ref``:

  tools:
    - ref: samples:tools/calc.tool.yaml       # kind: Tool manifest
    - ref: bundle://sre-tools/check-health    # ToolBundle entry
    - module_path: ./tools/my_tool.py          # inline anonymous (backward compat)

Tool manifests are also accepted inline inside ToolBundle entries: the
``impl:`` section mirrors the ``module_path`` / ``class_name`` fields that
``ToolEntry`` already carries, so the two are semantically equivalent.

Machine-readable schema:
    ``agent-runtime/src/mas/runtime/manifest/schema/tool.schema.yaml``

Human-readable reference:
    ``docs/manifests/mas-manifest-reference.md`` § kind: Tool
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# ToolParameter — one element of spec.parameters[]
# ---------------------------------------------------------------------------


@dataclass
class ToolParameter:
    """Declarative description of a single tool input parameter.

    Fields
    ------
    name:
        Parameter name — must be a valid Python identifier and match
        the ``**kwargs`` key passed to ``ToolContract.execute()``.

    type:
        JSON Schema primitive type: ``string | integer | number |
        boolean | array | object``.

    description:
        Human-readable explanation injected verbatim into the LLM tool
        spec (OpenAI ``function.parameters.properties.<name>.description``)
        and the MCP ``inputSchema``.  Write from the caller's perspective:
        "The name or URL of the service to check."

    required:
        When ``True`` the parameter is added to JSON Schema ``required[]``.
        Corresponds to ``Field(...)`` in Pydantic.

    default:
        Default value forwarded to the LLM spec.  Only meaningful when
        ``required`` is ``False``.

    enum:
        Restrict accepted values to this list.

    examples:
        Representative values shown in the LLM tool spec to improve
        sampling accuracy.  E.g. ``["2 + 3", "sqrt(16)", "100 / 4"]``.
    """

    name: str = ""
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = dataclasses.field(default=None)
    enum: List[Any] = field(default_factory=list)
    examples: List[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolParameter":
        return cls(
            name=data.get("name", ""),
            type=data.get("type", "string"),
            description=data.get("description", ""),
            required=bool(data.get("required", False)),
            default=data.get("default"),
            enum=list(data.get("enum") or []),
            examples=list(data.get("examples") or []),
        )

    def to_json_schema_property(self) -> Dict[str, Any]:
        """Return the JSON Schema property dict for this parameter.

        Used by :meth:`ToolSpec.to_json_schema` and
        :meth:`ToolSpec.to_openai_function_spec`.
        """
        prop: Dict[str, Any] = {"type": self.type}
        if self.description:
            prop["description"] = self.description
        if self.enum:
            prop["enum"] = self.enum
        if self.examples:
            prop["examples"] = self.examples
        if self.default is not None:
            prop["default"] = self.default
        return prop


# ---------------------------------------------------------------------------
# ToolImpl — spec.impl block
# ---------------------------------------------------------------------------


@dataclass
class ToolImpl:
    """Runtime implementation reference — hidden from LLM callers.

    Fields
    ------
    kind:
        ``python``   — a :class:`~mas.runtime.contracts.ToolContract` subclass
        loaded via ``module_path``.
        ``mcp``      — remote MCP tool; ``module_path`` points to the
        ``MCPClient`` adapter.
        ``openapi``  — OpenAPI endpoint; ``module_path`` points to the
        ``OpenAPITool`` adapter.

    module_path:
        Dotted Python module path or relative path, e.g.
        ``library-samples/tools/calc.py`` or ``./calc.py``.

    class_name:
        Class implementing ``ToolContract``.  Auto-discovered when ``None``
        (the runtime picks the first ``ToolContract`` subclass in the module).

    params:
        Optional constructor ``**kwargs`` forwarded to the class at
        instantiation time.
    """

    module_path: str = ""
    kind: str = "python"
    class_name: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolImpl":
        return cls(
            kind=data.get("kind", "python"),
            module_path=data.get("module_path", ""),
            class_name=data.get("class_name"),
            params=dict(data.get("params") or {}),
        )


@dataclass
class ToolEvent:
    """Declarative event emitted by a non-inline tool result flow.

    This stays intentionally generic:
    - ``stream`` tools emit incremental events
    - ``session`` tools emit events tied to a durable session handle
    """

    name: str = ""
    description: str = ""
    schema: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolEvent":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            schema=dict(data.get("schema") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"name": self.name}
        if self.description:
            data["description"] = self.description
        if self.schema:
            data["schema"] = self.schema
        return data


# ---------------------------------------------------------------------------
# ToolSpec — spec: block
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """``spec:`` block for ``kind: Tool``."""

    description: str = ""
    """Full description for LLM tool-use and MCP ``tool.description``."""

    parameters: List[ToolParameter] = field(default_factory=list)
    """Ordered list of input parameters — the semantic interface."""

    returns: Dict[str, Any] = field(default_factory=dict)
    """Return value description: ``{type, description}``."""

    idempotent: bool = False
    """True if the tool is safe to retry with the same arguments."""

    timeout_seconds: int = 30
    """Max allowed wall-clock execution time (seconds)."""

    execution_mode: str = "sync"
    """Execution contract: ``sync`` | ``async`` | ``realtime``."""

    result_mode: str = "inline"
    """Result contract: ``inline`` | ``stream`` | ``session``."""

    tool_category: Optional[str] = None
    """Optional semantic category surfaced to orchestrators and observers."""

    events: List[ToolEvent] = field(default_factory=list)
    """Event stream for ``stream`` or ``session`` result modes."""

    impl: Optional[ToolImpl] = None
    """Implementation reference — hidden from callers."""

    @classmethod
    def known_fields(cls) -> frozenset:
        return frozenset(f.name for f in dataclasses.fields(cls))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolSpec":
        raw_params = data.get("parameters") or []
        impl_data = data.get("impl")
        raw_events = data.get("events") or data.get("emits") or []
        return cls(
            description=data.get("description", ""),
            parameters=[ToolParameter.from_dict(p) for p in raw_params if isinstance(p, dict)],
            returns=dict(data.get("returns") or {}),
            idempotent=bool(data.get("idempotent", False)),
            timeout_seconds=int(data.get("timeout_seconds", 30)),
            execution_mode=data.get("execution_mode", "sync"),
            result_mode=data.get("result_mode", "inline"),
            tool_category=data.get("tool_category"),
            events=[ToolEvent.from_dict(item) for item in raw_events if isinstance(item, dict)],
            impl=ToolImpl.from_dict(impl_data) if impl_data else None,
        )

    # ------------------------------------------------------------------
    # Conversion helpers (semantic interface → wire formats)
    # ------------------------------------------------------------------

    def to_json_schema(self) -> Dict[str, Any]:
        """Build a JSON Schema ``object`` from ``spec.parameters[]``.

        This is the format expected by:
        - OpenAI function calling (``function.parameters``)
        - MCP ``inputSchema``
        - Pydantic's ``model_json_schema()`` output
        """
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for param in self.parameters:
            properties[param.name] = param.to_json_schema_property()
            if param.required:
                required.append(param.name)
        schema: Dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def to_openai_function_spec(self, name: str) -> Dict[str, Any]:
        """Build the OpenAI-compatible function spec dict.

        Returns the ``{type: function, function: {name, description, parameters}}``
        dict that can be passed directly to the ``tools`` kwarg of the
        OpenAI Chat Completions API.
        """
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": self.description,
                "parameters": self.to_json_schema(),
            },
        }

    def to_mcp_spec(self, name: str) -> Dict[str, Any]:
        """Build the MCP ``tool`` spec dict for ``/tools/list``."""
        return {
            "name": name,
            "description": self.description,
            "inputSchema": self.to_json_schema(),
        }

    def to_contract_dict(self, name: str) -> Dict[str, Any]:
        """Build a machine-readable public contract descriptor for the tool."""
        data: Dict[str, Any] = {
            "name": name,
            "description": self.description,
            "parameters": self.to_json_schema(),
            "returns": self.returns,
            "idempotent": self.idempotent,
            "timeout_seconds": self.timeout_seconds,
            "execution_mode": self.execution_mode,
            "result_mode": self.result_mode,
        }
        if self.tool_category:
            data["tool_category"] = self.tool_category
        if self.events:
            data["events"] = [event.to_dict() for event in self.events]
        return data


# ---------------------------------------------------------------------------
# ToolDocument — top-level kind: Tool document
# ---------------------------------------------------------------------------


@dataclass
class ToolDocument:
    """Parsed ``kind: Tool`` YAML document.

    Example::

        apiVersion: mas/v1
        kind: Tool

        metadata:
          name: calc
          description: "Evaluates arithmetic expressions."

        spec:
          description: >
            Evaluate an arithmetic expression and return the numeric result.
            Call this tool when the user wants to perform a calculation.

          parameters:
            - name: expression
              type: string
              description: "Arithmetic expression to evaluate, e.g. '2 + 3 * 4'."
              required: true
              examples:
                - "2 + 3"
                - "sqrt(16)"
                - "100 / 4"

          returns:
            type: string
            description: "The numeric result formatted as a string."

          idempotent: true
          timeout_seconds: 10

          impl:
            kind: python
            module_path: ./calc.py
            class_name: CalcTool
    """

    api_version: str
    metadata: Dict[str, Any]
    spec: ToolSpec

    @property
    def name(self) -> str:
        return self.metadata.get("name", "")

    @property
    def description(self) -> str:
        """Short metadata description (catalogue / dashboard label)."""
        return self.metadata.get("description", "")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolDocument":
        kind = str(data.get("kind") or "").strip()
        if kind and kind.lower() != "tool":
            raise ValueError(
                f"expected kind: Tool document, got kind: {kind!r}"
            )
        if not kind:
            raise ValueError("tool manifest missing kind: Tool")
        return cls(
            api_version=data.get("apiVersion", "mas/v1"),
            metadata=data.get("metadata", {}),
            spec=ToolSpec.from_dict(data.get("spec", {})),
        )

    def to_contract_dict(self, name: str) -> Dict[str, Any]:
        """Delegate to the underlying ToolSpec contract descriptor."""
        return self.spec.to_contract_dict(name)
