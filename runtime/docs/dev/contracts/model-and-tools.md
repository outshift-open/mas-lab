<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Model and Tool Contracts

This document covers the contracts most directly involved in model execution,
prompt retrieval, tool exposure, and memory-backed augmentation.

## ToolContract

`ToolContract` is the primary external action boundary.

### ToolContract purpose

- expose tools to an LLM or planner
- validate and normalize arguments
- execute a tool behind governance hooks

### ToolContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `get_name()` | none | Single-tool helper API |
| `get_description()` | none | Human-readable description |
| `get_parameters_schema()` | none | JSON Schema or schema derived from `Input` |
| `execute(**kwargs)` | validated tool args | Single-tool execution path |
| `list_tools()` | none | Returns LLM-visible tool descriptors |
| `call_tool(tool_name, arguments)` | tool name, dict arguments | Composite or single-tool dispatch |

### ToolContract runtime call path

```text
collect_tools
  -> ToolContract.list_tools()

execute_tool
  -> BudgetContract.on_pre_tool_call()
  -> ToolContract.call_tool()
  -> RecorderContract.emit()
```

### ToolContract example

```python
from pydantic import BaseModel, Field
from mas.runtime.contracts import ToolContract


class CheckHealthTool(ToolContract):
    class Input(BaseModel):
        service_name: str = Field(..., description="Service name or URL")

    def get_name(self) -> str:
        return "check-service-health"

    def get_description(self) -> str:
        return "Check whether a service is healthy."

    def execute(self, **kwargs):
        args = self.Input(**kwargs)
        return {"healthy": True, "service": args.service_name}
```

## PromptContract

`PromptContract` abstracts prompt lookup and late prompt mutation.

### PromptContract purpose

- fetch prompts by identifier, name, or path
- centralize prompt versioning or approval logic
- allow prompt post-processing through hooks

### PromptContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `fetch_prompt(prompt_ref)` | prompt reference dict | Core retrieval method |
| `pre_prompt_build(context)` | prompt ref, agent, session | Optional validation and selection |
| `post_prompt_build(context)` | prompt text, agent, prompt ref | Optional mutation stage |

Typical `prompt_ref` shapes:

```python
{"id": "greeting"}
{"name": "greeting"}
{"prompt_id": "greeting"}
{"path": "/path/to/prompt.yaml"}
```

### PromptContract example

```python
from mas.runtime.contracts import PromptContract


class StaticPromptProvider(PromptContract):
    def fetch_prompt(self, prompt_ref):
        prompt_id = prompt_ref.get("id") or prompt_ref.get("name")
        if prompt_id == "greeting":
            return "You are a concise support assistant."
        raise KeyError(prompt_ref)
```

## MemoryContract

`MemoryContract` handles semantic, episodic, and procedural memory I/O.

### MemoryContract purpose

- expose a persistent memory backend behind hooks
- support provenance and versioning
- separate memory from session state and shared coordination state

### MemoryContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `read_memory(memory_type, query)` | memory type, query dict | Query memory backend |
| `write_memory(memory_type, payload)` | memory type, payload dict | Persist memory item |
| `pre_memory_store(context)` | write context | Optional quota or schema checks |
| `post_memory_store(context)` | result context | Optional audit or replication |

Supported memory types in the current contract documentation:

- `episodic`
- `semantic`
- `procedural`

### MemoryContract example

```python
from mas.runtime.contracts import DummyMemoryStore

memory = DummyMemoryStore()
memory.write_memory(
    "episodic",
    {
        "key": "turn-001",
        "content": {"summary": "User asked for deployment status."},
        "metadata": {"agent_id": "ops-agent"},
    },
)
```

## ModelContract

`ModelContract` is the provider-backed model execution boundary.

### ModelContract purpose

- advertise available model providers
- execute chat completions behind a uniform API
- normalize content, usage, tool calls, and thinking traces

### ModelContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `on_collect_models()` | none | Reports provider availability |
| `complete(model, messages, temperature, max_tokens, tools=None)` | model name, message list, sampling settings, optional tool specs | Main generation method |
| `supports_tool_calling` | property | Whether native tool calling is supported |
| `available` | property | Whether backend is ready |

### ModelContract response shape

`LLMResponse` standardizes:

- `content`
- `usage`
- `tool_calls`
- `thinking`
- `finish_reason`

### ModelContract example

```python
from mas.runtime.contracts import ModelContract, LLMResponse


class MockModel(ModelContract):
    provider_id = "mock"

    @property
    def available(self) -> bool:
        return True

    def complete(self, model, messages, temperature=0.7, max_tokens=1500, tools=None):
        return LLMResponse(content="mock response")
```

### ModelContract backward compatibility note

`ModelContract` is currently an alias of `ModelContract`. New code should
prefer `ModelContract`.
