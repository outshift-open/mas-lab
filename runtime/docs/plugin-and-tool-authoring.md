<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Agent Runtime — Plugin & Tool Authoring Guide

> **Audience**: developers building plugins, tools, or surface adapters for
> `mas-runtime`.  Covers the full authoring lifecycle from zero-ceremony
> `@plugin` decorator to governance hooks and observability wiring.

---

## Table of Contents

1. [Quick Start: Your First Plugin in 10 Lines](#1-quick-start)
2. [The @plugin Decorator](#2-the-plugin-decorator)
3. [Tool Authoring](#3-tool-authoring)
   - [Style A — Pydantic Input (recommended)](#style-a--pydantic-input)
   - [Style B — Manual JSON Schema](#style-b--manual-json-schema)
4. [Built-in Tool Library](#4-built-in-tool-library)
5. [Contract Taxonomy Cheat Sheet](#5-contract-taxonomy)
6. [Surface adapters](#6-surface-adapters)
7. [Observability: What Gets Emitted](#7-observability)
   - [context_part_contributed (L4)](#context_part_contributed)
   - [governance_checked / governance_denied (L6)](#governance-events)
8. [Governance Integration](#8-governance-integration)
9. [Packaging & Installation](#9-packaging)

---

## 1. Quick Start

```python
from mas.runtime.contracts import plugin, ToolContract

@plugin
class GreeterTool(ToolContract):
    def get_name(self):
        return "greet"

    def get_description(self):
        return "Greet someone by name."

    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name to greet."}
            },
            "required": ["name"],
        }

    def execute(self, **kwargs):
        return {"message": f"Hello, {kwargs['name']}!"}
```

That's it.  No `plugin_id`, no `implements`, no `ClassVar` declarations.
The `@plugin` decorator infers everything:

```python
>>> GreeterTool.plugin_id
'greeter@v1'
>>> GreeterTool.implements
['tool']
```

---

## 2. The @plugin Decorator

### What it does

| Field | Auto-inferred from | Override syntax |
|-------|-------------------|----------------|
| `plugin_id` | Class name → `snake_case@v1` (strips `Tool`/`Plugin` suffix) | `@plugin(plugin_id="my_id@v2")` or set `plugin_id = "..."` as ClassVar |
| `implements` | MRO walk — collects `contract_id` from all parent contracts | Set `implements = [...]` as ClassVar |
| `requires` | *(not inferred)* | `@plugin(requires=["recorder"])` |
| `governed_by` | *(not inferred)* | `@plugin(governed_by=["budget"])` |

### Name conversion rules

| Class Name | Auto plugin_id |
|-----------|---------------|
| `DateTimeTool` | `date_time@v1` |
| `MyHTTPClientPlugin` | `my_http_client@v1` |
| `BudgetGovernance` | `budget_governance@v1` |
| `SimplePlugin` | `simple@v1` |

### Usage forms

```python
# Form 1: bare decorator (most common)
@plugin
class MyTool(ToolContract): ...

# Form 2: with explicit overrides
@plugin(requires=["recorder"], governed_by=["budget"])
class MyTool(ToolContract): ...

# Form 3: mixed — decorator + ClassVar override
@plugin
class MyTool(ToolContract):
    plugin_id = "my_custom_id@v3"  # this takes precedence
    implements = ["tool", "custom"]  # this takes precedence
```

### Multi-contract plugins

When a plugin inherits from multiple contracts, `@plugin` discovers all of them:

```python
@plugin
class SmartMemoryTool(ToolContract, MemoryContract):
    ...

>>> SmartMemoryTool.implements
['tool', 'memory']
```

### Import

```python
from mas.runtime.contracts import plugin
# or
from mas.runtime.contracts.base import plugin
```

---

## 3. Tool Authoring

All tools inherit from `ToolContract`.  Two styles are supported.

### Style A — Pydantic Input

```python
from pydantic import BaseModel, Field
from mas.runtime.contracts import plugin, ToolContract

@plugin
class WeatherTool(ToolContract):
    class Input(BaseModel):
        city: str = Field(..., description="City name")
        units: str = Field("metric", description="metric or imperial")

    def get_name(self):
        return "weather"

    def get_description(self):
        return "Get current weather for a city."

    # get_parameters_schema() is auto-derived from Input.model_json_schema()
    # No need to override it!

    def execute(self, **kwargs):
        args = self.Input(**kwargs)  # Pydantic validation
        return {"city": args.city, "temp": 22, "units": args.units}
```

### Style B — Manual JSON Schema

```python
@plugin
class CalculatorTool(ToolContract):
    def get_name(self):
        return "calculator"

    def get_description(self):
        return "Evaluate a math expression."

    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression to evaluate (e.g. '2 + 3 * 4')"
                }
            },
            "required": ["expression"],
        }

    def execute(self, **kwargs):
        # ... safe evaluation logic ...
        return {"result": 42}
```

### Tool lifecycle

```
collect_tools hook
  └─ ToolContract.on_collect_tools()
      └─ returns [{name, description, parameters}]

execute_tool hook
  └─ ToolContract.on_execute_tool(tool_name, arguments)
      └─ ToolContract.call_tool(name, args)
          └─ ToolContract.execute(**args)
```

---

## 4. Built-in Tool Library

All tools live in `mas.runtime.tools` and use `@plugin`.  Zero external
dependencies — they use only the Python standard library.

### DateTimeTool

```python
from mas.runtime.tools import DateTimeTool

tool = DateTimeTool()
tool.execute()
# → {"datetime": "2026-04-11T13:00:31.566334+00:00", "format": "iso"}

tool.execute(format="unix")
# → {"timestamp": 1744376431.5, "format": "unix"}

tool.execute(format="%Y-%m-%d", timezone="+05:30")
# → {"datetime": "2026-04-11", "format": "%Y-%m-%d"}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | `"iso"` | `"iso"`, `"unix"`, or any `strftime` pattern |
| `timezone` | string | `"utc"` | `"utc"` or UTC offset like `"+05:30"` |

### JsonTool

```python
from mas.runtime.tools import JsonTool

tool = JsonTool()

# Parse
tool.execute(operation="parse", data='{"a": 1}')
# → {"status": "ok", "result": {"a": 1}}

# Dot-path extraction
tool.execute(operation="get", data='{"user": {"name": "Alice"}}', path="user.name")
# → {"status": "ok", "result": "Alice"}

# Pretty-print
tool.execute(operation="format", data='{"a":1,"b":2}')
# → {"status": "ok", "result": "{\n  \"a\": 1,\n  \"b\": 2\n}"}

# Merge objects
tool.execute(operation="merge", data='{"a": 1}', merge_with='{"b": 2}')
# → {"status": "ok", "result": {"a": 1, "b": 2}}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `operation` | string | yes | `"parse"`, `"format"`, `"get"`, `"merge"` |
| `data` | string | yes | JSON string to process |
| `path` | string | for `get` | Dot-separated path (e.g. `"user.name"`, `"items.0"`) |
| `merge_with` | string | for `merge` | Second JSON string |

### TextTool

```python
from mas.runtime.tools import TextTool

tool = TextTool()

tool.execute(operation="count", text="Hello world")
# → {"characters": 11, "words": 2, "lines": 1}

tool.execute(operation="search", text="Error: 404, Error: 500", pattern=r"Error: (\d+)")
# → {"status": "ok", "count": 2, "matches": [...]}

tool.execute(operation="replace", text="Hello world", pattern="world", replacement="earth")
# → {"status": "ok", "result": "Hello earth"}

tool.execute(operation="extract", text="Call 123-456 or 789-012", pattern=r"\d{3}-\d{3}")
# → {"status": "ok", "matches": ["123-456", "789-012"]}

tool.execute(operation="truncate", text="a" * 200, max_length=50)
# → {"status": "ok", "result": "aaaa...…", "truncated": true}
```

| Operation | Parameters | Description |
|-----------|-----------|-------------|
| `count` | `text` | Word, character, and line counts |
| `search` | `text`, `pattern` | Regex search with match positions |
| `replace` | `text`, `pattern`, `replacement` | Regex replace |
| `extract` | `text`, `pattern` | Extract all regex matches |
| `split` | `text`, `delimiter` | Split by delimiter |
| `truncate` | `text`, `max_length` | Truncate with ellipsis |

### HttpTool

```python
from mas.runtime.tools import HttpTool

tool = HttpTool()

tool.execute(url="https://api.example.com/data", method="GET")
# → {"status": "ok", "status_code": 200, "headers": {...}, "body": {...}}

tool.execute(
    url="https://api.example.com/items",
    method="POST",
    body='{"name": "Widget"}',
    headers={"Authorization": "Bearer token123"},
)
```

**Security features:**

- **SSRF protection**: blocks `localhost`, `127.0.0.1`, `::1`, `10.x.x.x`,
  `172.16-31.x.x`, `192.168.x.x`, `169.254.169.254` (cloud metadata)
- **Response size limit**: 1 MB max
- **Timeout**: configurable, max 120 seconds

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `url` | string | yes | — |
| `method` | string | no | `"GET"` |
| `headers` | object | no | `{}` |
| `body` | string | no | — |
| `query_params` | object | no | — |
| `timeout` | integer | no | 30 |

### FileOpsTool and ShellTool (internal only)

Filesystem and shell tools with sandbox governance are **not** part of the OSS
release. They ship in `mas-lab-internal` with `SandboxContract` enforcement.

### Tool summary

| Tool | Name | Key operations | External deps | Governance |
|------|------|---------------|---------------|------------|
| `DateTimeTool` | `datetime` | ISO, Unix, strftime, timezone | None | — |
| `JsonTool` | `json` | parse, format, get, merge | None | — |
| `TextTool` | `text` | count, search, replace, extract, split, truncate | None | — |
| `HttpTool` | `http` | GET, POST, PUT, DELETE | None | SSRF built-in |
| `CalculatorTool` | `calculator` | safe math evaluation | None | — |
| `WebSearchTool` | `web_search` | cached web search | None | — |
| `VerifyFactTool` | `verify_fact` | fact verification | None | — |
| `MemorySearchTool` | `memory_search` | semantic memory search | None | — |
| `MemoryGetTool` | `memory_get` | key-value memory retrieval | None | — |
| `GetScheduleTool` | `get_schedule` | schedule lookup | None | — |
| `GetAttractionsTool` | `get_attractions` | attraction lookup | None | — |

---

## 5. Contract Taxonomy

```
ContractBase
├── CapabilityContract  — WHAT the agent can access (20 contracts)
│   ├── ToolContract        (tool)
│   ├── PromptContract      (prompt)
│   ├── MemoryContract      (memory)
│   ├── SensorContract      (sensor)
│   ├── SessionContract     (session)
│   ├── ExecutionSessionContract (execution)
│   ├── TransportContract   (transport)
│   ├── MessageContract     (message)
│   ├── RecorderContract    (recorder)
│   ├── ControlContract     (control)
│   ├── SharedContextContract (shared_context)
│   ├── DelegationContract  (delegation)
│   ├── ModelAccessContract (model_access)
│   ├── ContextContract     (context — BasePlugin mixin)
│   ├── LLMContract         (llm)
│   ├── DesignPatternContract (dp)
│   ├── GatewayContract     (gateway)
│   └── SurfaceAdapter      (surface)
│
├── OrchestrationContract  — HOW control flows
│   └── WorkflowContract    (workflow)
│
└── GovernanceContract      — POLICY over capabilities
    ├── BudgetContract      (budget)
    └── RoutingContract     (routing)
    # SandboxContract, TBACContract — mas-lab-internal only
```

---

## 6. Surface adapters

> **Evolution (L8)** is not in OSS — internal extension only.

### SurfaceAdapter (multi-surface)

Connects external delivery surfaces (Slack, web, CLI, agent-remote) to the runtime
through the hook system.

```python
from mas.runtime.contracts import plugin, SurfaceAdapter, SurfaceEnvelope

@plugin
class SlackAdapter(SurfaceAdapter):
    @property
    def surface_type(self):
        return "slack"

    def ingest(self, raw_event):
        """Convert a Slack event → SurfaceEnvelope."""
        return SurfaceEnvelope(
            surface_type="slack",
            channel_id=raw_event["channel"],
            sender_id=raw_event["user"],
            thread_id=raw_event.get("thread_ts", ""),
            content=raw_event["text"],
        )

    def deliver(self, envelope, response):
        """Send agent response back to Slack."""
        # slack_client.chat_postMessage(
        #     channel=envelope.channel_id,
        #     text=response.get("content", ""),
        #     thread_ts=envelope.thread_id,
        # )
        pass

    def start(self):
        """Start the Slack event listener."""
        pass

    def stop(self):
        """Stop the listener."""
        pass
```

**SurfaceEnvelope fields:**

| Field | Type | Description |
|-------|------|-------------|
| `surface_type` | str | `"slack"`, `"discord"`, `"web"`, `"cli"`, `"agent-remote"` |
| `channel_id` | str | Surface-native channel ID |
| `sender_id` | str | Surface-native sender ID |
| `thread_id` | str | Thread/conversation ID |
| `content` | str | Message text content |
| `attachments` | List[Dict] | File attachments |
| `metadata` | Dict | Arbitrary surface metadata |

---

## 7. Observability

### ContextPart and part_id (L4)

Every `ContextPart` now has a unique `part_id` (UUID v4), auto-generated
at construction time:

```python
from mas.runtime.contracts import ContextPart

part = ContextPart(content="Remember this fact", source="memory")
print(part.part_id)
# → "fba8fb4a-9bf8-41c4-a9ab-ed85dac0fab8"

# In the observability dict:
obs = part.to_observability_dict()
assert obs["part_id"] == part.part_id
```

### context_part_contributed

The context assembler emits a `context_part_contributed` event **per
part** (retained and evicted) to the agent's recorder.  This enables
token-level attribution — you can trace exactly why each token is in the
prompt.

**Retained part event:**

```json
{
    "kind": "context_part_contributed",
    "agent_id": "sre-agent",
    "timestamp": 1744376431.5,
    "part_id": "fba8fb4a-...",
    "source": "memory:episodic",
    "section_id": "memory/episode-42",
    "mechanism": "memory_read",
    "cause": "dp_intent",
    "cause_type": "memory",
    "token_estimate": 150,
    "retained": true
}
```

**Evicted part event:**

```json
{
    "kind": "context_part_contributed",
    "agent_id": "sre-agent",
    "timestamp": 1744376431.5,
    "source": "skills",
    "section_id": "skills/network-analysis",
    "token_estimate": 400,
    "retained": false,
    "eviction_reason": "budget_exceeded"
}
```

### Governance Events

#### governance_checked (L6 — silent allows)

Emitted after all blocking hooks on a hook point complete **without
raising**.  Previously, success was invisible.  Now it's auditable.

```json
{
    "kind": "governance_checked",
    "hook": "pre_llm_call",
    "checks_passed": 3,
    "outcome": "allowed"
}
```

When emitted: after the hook loop for any **blocking** hook point completes
without exception.  Not emitted for non-blocking hooks or when no hooks are
registered.

#### governance_denied (L6 — explicit denial)

Emitted when a `PolicyViolation` is raised by a governance plugin.
Distinguishes governance denial from technical errors.

```json
{
    "kind": "governance_denied",
    "hook": "pre_llm_call",
    "plugin": "BudgetPlugin",
    "contract_id": "budget",
    "reason": "Token ceiling exceeded",
    "details": {"remaining": 0, "requested": 500}
}
```

Contrast with `hook_error` (technical failure):

```json
{
    "kind": "hook_error",
    "hook": "pre_llm_call",
    "plugin": "LLMAdapter",
    "error": "Connection refused"
}
```

**Decision logic in `_emit_hook_error`:**

```
Exception caught in hook dispatch
  ├─ Is it a PolicyViolation? → emit governance_denied
  └─ Otherwise? → emit hook_error
```

---

## 8. Governance Integration

### How governance hooks work

```
Agent requests LLM call
  ↓
pre_llm_call hook fires (BLOCKING)
  ↓
Plugin 1: BudgetPlugin.on_pre_llm_call() → checks token ceiling
  ├─ OK → continue to next plugin
  └─ DENY → raise PolicyViolation → governance_denied event → STOP
...
All plugins passed → governance_checked event emitted
  ↓
LLM call proceeds
```

### Declaring governance requirements

```python
@plugin(governed_by=["budget"])
class RateLimitedTool(ToolContract):
    ...
```

This declaration is informational metadata — governance contracts hook into
the same hook points and run automatically.

### Writing a custom governance plugin

```python
from mas.runtime.contracts.base import GovernanceContract, PolicyViolation

class RateLimitGovernance(GovernanceContract):
    contract_id = "rate_limit"

    def __init__(self, max_calls_per_minute=60):
        super().__init__()
        self._max = max_calls_per_minute
        self._calls = []

    def on_pre_llm_call(self, data=None, **kw):
        import time
        now = time.time()
        self._calls = [t for t in self._calls if now - t < 60]
        if len(self._calls) >= self._max:
            raise PolicyViolation(
                contract_id="rate_limit",
                reason=f"Rate limit exceeded: {self._max}/min",
                details={"current_count": len(self._calls)},
            )
        self._calls.append(now)
```

---

## 9. Packaging

### Optional dependency groups

```bash
# Core only (minimal)
uv pip install -e mas-runtime

# OpenTelemetry export (internal / mas-lab-internal only — not an OSS extra)
# uv pip install -e "mas-runtime[otel]"  # see mas-lab-internal

# With RAG (llama-index)
uv pip install -e "mas-runtime[rag]"

# With gRPC transport
uv pip install -e "mas-runtime[grpc]"

# Everything
uv pip install -e "mas-runtime[all]"
```

| Extra | Packages included |
|-------|-------------------|
| `otel` | `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` |
| `rag` | `llama-index-core`, `llama-index-readers-file` |
| `grpc` | `grpcio`, `grpcio-tools` |
| `all` | All of the above |
| `test` | `pytest`, `pytest-asyncio`, `hypothesis`, `jinja2` |

### Install

```bash
uv pip install -e mas-runtime -e mas-lab
```

---

## Hook Reference (35 hooks)

| Hook | Blocking | Modification | Category |
|------|----------|-------------|----------|
| `pre_execution` | Yes | Yes | Execution |
| `post_execution` | No | No | Execution |
| `pre_llm_call` | Yes | Yes | LLM |
| `post_llm_call` | No | Yes | LLM |
| `pre_tool_call` | Yes | Yes | Tool |
| `post_tool_call` | No | Yes | Tool |
| `collect_tools` | No | No | Tool |
| `execute_tool` | No | No | Tool |
| `pre_prompt_build` | Yes | Yes | Prompt |
| `post_prompt_build` | No | Yes | Prompt |
| `pre_memory_store` | Yes | Yes | Memory |
| `post_memory_store` | No | No | Memory |
| `pre_agent_communication` | Yes | Yes | Communication |
| `post_agent_communication` | No | No | Communication |
| `pre_sensor_event` | Yes | Yes | Sensor |
| `post_sensor_event` | No | No | Sensor |
| `pre_session_access` | Yes | Yes | Session |
| `post_session_access` | No | No | Session |
| `on_pre_checkpoint` | Yes | No | Execution |
| `on_post_checkpoint` | No | No | Execution |
| `on_pre_restore` | Yes | No | Execution |
| `on_post_restore` | No | No | Execution |
| `pre_agent_handoff` | Yes | Yes | Communication |
| `post_agent_handoff` | No | No | Communication |
| `pre_context_assembly` | No | Yes | Context |
| `post_context_assembly` | No | No | Context |
| `collect_context` | No | No | Context |
| `on_error` | No | No | Error |
| `user_input` | Yes | Yes | I/O |
| `user_output` | Yes | Yes | I/O |
| `object_model_event` | No | No | KG |
| `skills_check` | No | No | Skills |

---

## Test Coverage

| Test file | Tests | What it covers |
|-----------|-------|---------------|
| `test_plugin_decorator.py` | 13 | `@plugin` auto-inference, overrides, ClassVar preservation, multi-contract |
| `test_tool_libraries.py` | 41 | All 6 new tools: DateTime, Json, Text, FileOps, Shell, Http |
| `test_governance_visibility.py` | 8 | governance_checked, governance_denied, denial chain behavior |
| `test_l4_part_id_and_provenance.py` | 17 | part_id generation, context_part_contributed events, eviction |

**Total: 1760 tests passing, 0 failures, 0 skips.**
