<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Messaging and Orchestration Contracts

This document covers inbound signals, inter-agent communication, agent
delegation, and the MAS execution loop.

## SensorContract

`SensorContract` is the inbound signal boundary.

### SensorContract purpose

- normalize world-to-agent signals
- support pull and push event models
- provide channel-specific reply handling

### SensorContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `get_source()` | none | Source name such as `telegram` or `cli` |
| `get_modality()` | none | Modality such as `text` or `image` |
| `pull()` | none | Async pull model |
| `emit_event(event)` | `SensorEvent` | Push model enqueue |
| `push_reply(session_id, content)` | session ID, reply content | Channel-specific reply path |

### SensorContract core event parameters

`SensorEvent` contains:

- `source`
- `modality`
- `content`
- `session_id`
- `contact_id`
- `timestamp`
- `metadata`
- `raw`

### SensorContract example

```python
from mas.runtime.contracts import SensorContract, SensorEvent


class CliSensor(SensorContract):
    def get_source(self) -> str:
        return "cli"

    async def pull(self):
        return SensorEvent(
            source="cli",
            modality="text",
            content="run deployment check",
            session_id="cli:demo",
            contact_id="user:alice",
        )
```

## MessageContract

`MessageContract` provides simple inter-agent messaging.

### MessageContract purpose

- send typed payloads with correlation IDs
- support simple messaging independent of transport details
- provide a low-friction contract beside richer agent-remote protocols

### MessageContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `send_message(target_agent_id, message, correlation_id=None)` | target ID, message dict, optional correlation ID | Async send API |
| `receive_message(message)` | incoming message dict | Optional receive hook |
| `pre_agent_communication(context)` | target, message, source, optional correlation ID | Validation and defaults |
| `post_agent_communication(context)` | send result context | Audit or telemetry |

### MessageContract minimal message fields

The default validation expects:

- `intent_type`
- `payload`

It also injects:

- `schema_version`
- `correlation_id`

### MessageContract example

```python
from mas.runtime.contracts import MessageContract


class StubMessenger(MessageContract):
    async def send_message(self, target_agent_id, message, correlation_id=None):
        return {
            "status": "sent",
            "target_agent_id": target_agent_id,
            "correlation_id": correlation_id or "generated-id",
        }
```

## TransportContract

`TransportContract` handles the physical delivery path for inter-agent traffic.

### TransportContract purpose

- decouple delivery transport from message semantics
- let agent-remote or other messaging plugins swap transport implementations

### TransportContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `start()` | none | Async startup |
| `stop()` | none | Async shutdown |
| `send(recipient, content, msg_type=..., priority=..., in_reply_to=None, wait_for_response=False, timeout=30.0)` | recipient, payload, delivery metadata | Raw transport send |
| `is_ready` | property | Startup state |

### TransportContract example

```python
from mas.runtime.contracts import InMemoryTransport, MessageType


transport = InMemoryTransport()
# await transport.start()
# await transport.send("agent-B", {"task": "inspect"}, msg_type=MessageType.REQUEST)
```

## DelegationContract

`DelegationContract` exposes agents as callable tools and prompt-visible delegates.

### DelegationContract purpose

- render sub-agents as tool specs
- call sub-agents through a uniform delegation surface
- contribute an "Available Agents" section to prompt assembly

### DelegationContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `_resolve_delegates()` | none | Implemented by concrete subclass |
| `delegate(target_agent_id, task, context=None, correlation_id=None, parent_exec_call_id=None)` | target ID, natural-language task, optional context and tracing info | Core delegation operation |
| `list_tools()` | none | Creates `delegate_to_*` tool specs |
| `call_tool(tool_name, arguments)` | delegate tool name and LLM arguments | Dispatches to `delegate()` |
| `collect_context()` | none | Adds available-agent directory to the prompt |

### DelegationContract example

```python
from mas.runtime.contracts import LocalAgentDelegate

# Concrete LocalAgentDelegate instances resolve delegates from manifests and
# call sub-agents in-process via handle_task().
```

## WorkflowContract

`WorkflowContract` is the MAS execution topology boundary.

### WorkflowContract purpose

- choose how agents are invoked for a request
- keep control-flow topology separate from agent reasoning
- let the runtime swap dynamic, supervised, and sequential workflows

### WorkflowContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `register_impl(name, impl_cls)` | workflow name and implementation class | Factory registration |
| `build(name="dynamic", **kwargs)` | workflow name and constructor args | Factory constructor |
| `run(runtime, task)` | runtime context and task dict | Core orchestration method |
| `on_turn_boundary(turn_number, state)` | turn index and `TurnBoundaryState` snapshot | Optional hook called between turns — governance or evaluation can inspect and abort |

### WorkflowContract example

```python
from mas.runtime.contracts import WorkflowContract

# wf = WorkflowContract.build("dynamic")
# result = wf.run(runtime, {"prompt": "triage this incident"})
```

## Messaging and orchestration call path

```text
SensorContract.pull() or emit_event()
  -> SessionContract.load_session()
  -> WorkflowContract.run()
  -> DelegationContract.list_tools() and collect_context()
  -> MessageContract.send_message() or TransportContract.send()
```
