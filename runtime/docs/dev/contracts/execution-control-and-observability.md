<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Execution Control and Observability Contracts

This document covers runtime control and structured event recording.

## ControlContract

`ControlContract` is the pluggable execution control plane.

### ControlContract purpose

- pause or resume execution
- abort runs with explicit reasons
- create and restore checkpoints
- inject steering directives into active runs

### ControlContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `pause(reason=None, agent_id=None)` | optional reason and agent | Temporary halt |
| `resume(agent_id=None)` | optional agent | Resume paused run |
| `abort(reason=None, agent_id=None)` | optional reason and agent | Permanent stop |
| `checkpoint(label=None)` | optional label | Returns checkpoint metadata |
| `restore_checkpoint(checkpoint_id)` | checkpoint ID | Roll back to checkpoint |
| `steer(directive, agent_id=None, priority="normal")` | directive text, optional target, priority | Mid-flight steering |
| `drain_steering(agent_id=None)` | optional target | Consumed before next LLM step |

### ControlContract hook helpers

- `pre_control_action(action, reason, agent_id)`
- `post_control_action(action, success, agent_id)`

### ControlContract example

```python
from mas.runtime.contracts import ControlContract


def interrupt_for_review(control: ControlContract):
    control.pause(reason="Human approval required", agent_id="agent-123")
```

## RecorderContract

`RecorderContract` is the structured event-recording boundary.

### RecorderContract purpose

- capture hook and runtime events
- support pluggable backends such as JSONL or OpenTelemetry
- keep observability detached from business logic

### RecorderContract primary methods and parameters

| Method | Parameters | Notes |
| --- | --- | --- |
| `emit(event)` | event dict | Core write operation |
| `flush()` | none | Flush buffered events |
| `close()` | none | Close resources |
| `query(*, kind, agent_id, since, until, call_id, extra_filter)` | all optional | Read back recorded events matching filters |
| `replay(from_call_id)` | optional call ID | Replay events from a point onwards |

### RecorderContract typical event parameters

Common fields described by the contract include:

- `kind`
- `timestamp`
- `trace_id`
- `span_id`
- `parent_span_id`
- `agent_id`
- `hook_name`
- `plugin_name`
- `error`
- `metadata`

### RecorderContract example

```python
from mas.runtime.contracts import RecorderContract


def emit_tool_event(recorder: RecorderContract):
    recorder.emit(
        {
            "kind": "hook_start",
            "hook_name": "pre_tool_call",
            "plugin_name": "sandbox",
            "agent_id": "agent-123",
            "timestamp": 0.0,
        }
    )
```

## Control and recorder interaction

```text
ControlContract.pause()
  -> runtime pauses at a safe boundary
  -> RecorderContract.emit() records the intervention

ControlContract.steer()
  -> runtime drains directives before the next LLM step
  -> RecorderContract.emit() records the steering event
```
