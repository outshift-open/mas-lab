# Implementation Plan: Agent-Driven HITL Side Channel

## Discovery Summary

### Current HITL Architecture (Working but Limited)

1. **Governance-triggered HITL** (`hitl_on_tool`):
   - Works via governance plugins
   - Emits `EmitHitlRequest` in governance hooks
   - `SessionController._drain_hitl()` resolves via local `HitlTerminal`
   - ✅ **Works** because everything is in same process

2. **Delegation Flow** (mas_session.py::send()):
   ```python
   result = controller.run_turn(prompt, turn_id=turn_id, parent_call_id=parent_call_id)
   ...
   return result.text  # ⚠️ LOSES result.awaiting_hitl
   ```
   - Sub-agent's `awaiting_hitl` state is DISCARDED
   - Caller (moderator) never knows HITL is pending
   - **Broken for distributed MAS**: no way to propagate HITL request up

3. **The Side Channel Problem**:
   - Current HITL blocks the LOCAL agent via `_drain_hitl` loop
   - No mechanism for **asynchronous external resolution**
   - In distributed MAS: HITL request would be invisible to entry point

### Why This Breaks in Distributed MAS

```
┌─────────────────┐
│  Moderator      │  runs in Process A
│  (entry agent)  │
└────────┬────────┘
         │ delegate("finance", "analyze discount")
         ▼
┌─────────────────┐
│  Finance Agent  │  runs in Process B (different machine)
│                 │  
│  calls:         │
│  request_human_input("Approve 20%?")
│                 │
│  result.awaiting_hitl = True  ◄── THIS STATE NEVER LEAVES PROCESS B
│                 │
│  return result.text  ← "delegated result text"
└─────────────────┘
         │
         │ send() returns text only
         ▼
┌─────────────────┐
│  Moderator      │  ⚠️ HAS NO IDEA finance is awaiting HITL
│  continues...   │  ⚠️ User never sees the question
└─────────────────┘
```

## Solution Architecture

### Phase 1: Side-Channel HITL Resolver (✅ COMPLETE)

**Created Files**:
- [system_tools/request_human_input.py](../../runtime/src/mas/runtime/system_tools/request_human_input.py) — System tool contract
- [system_tools/signal.py](../../runtime/src/mas/runtime/system_tools/signal.py) — `RequestHitlSignal` exception
- [docs/design/agent-driven-hitl.md](agent-driven-hitl.md) — Architecture doc

**Implementation Approach**:

Instead of modifying kernel internals, use **governance plugin pattern**:

1. Create `SystemToolsPlugin` (governance plugin)
2. Plugin provides `request_human_input` tool
3. Plugin's `on_execute_tool` catches `RequestHitlSignal`
4. Converts signal to `EmitHitlRequest` via existing APIs
5. Returns special marker that tells runtime to pause

**Benefits**:
- Uses existing governance infrastructure
- No kernel modifications needed
- Clean separation: tool → plugin → governance emission

### Phase 2: Delegation Propagation (✅ COMPLETE)

**Modified Files**:
- `runtime/src/mas/runtime/boundary/hitl/registry.py` — NEW: Thread-safe HITL resolver registry
- `runtime/src/mas/runtime/engine/manifest_tool_provider.py` — Inject system tools + wrapper
- `runtime/src/mas/runtime/engine/tool_dispatch.py` — HITL marker detection
- `runtime/src/mas/runtime/driver/mocks.py` — Add session_id/agent_id to ctx
- `runtime/src/mas/runtime/driver/driver.py` — Propagate session_id/agent_id to ctx
- `ctl/src/mas/ctl/executor/mas_session.py` — Track pending HITL in delegation state

**Flow**:

```python
# Agent calls tool:
request_human_input(question="Approve 20%?", question_type="CONFIRM", ...)

# Tool raises signal:
raise RequestHitlSignal(question=..., question_type=..., ...)

# Wrapper catches signal:
def on_execute_tool(...):
    try:
        return self._tool.execute(**arguments)
    except RequestHitlSignal as signal:
        # Register in global registry
        registry.register(
            session_id=ctx.session_id,
            agent_id=ctx.agent_id,
            correlation_id=ctx.correlation_id,
            ...
        )
        # Return marker
        return {"__hitl_request__": True, ...}

# Runtime detects marker:
if is_hitl_marker(result):
    metadata = extract_hitl_metadata(result)
    # External system polls pending HITL

# Delegation propagates state:
if result.awaiting_hitl:
    registry.has_pending(session_id, agent_id)
    state["pending_hitl_agents"].add(agent_id)
```

### Phase 3: Webex Bot Integration (✅ COMPLETE)

**Added Files**:
- `webex-use-case/src/webex_use_case/hitl_helpers.py` — HITL detection/resolution helpers

**Helper Functions**:
```python
get_pending_hitl_for_session(session_id) -> dict[agent_id, list[requests]]
resolve_agent_hitl(session_id, agent_id, correlation_id, choice, steering)
has_pending_hitl(session_id, agent_id=None) -> bool
clear_session_hitl(session_id)
```

**Integration Pattern**:

```python
# In webex bot _handle_room_text:
result = session.ask(text)

# Check for pending HITL
from webex_use_case.hitl_helpers import get_pending_hitl_for_session

pending = get_pending_hitl_for_session(result.session_id)
for agent_id, requests in pending.items():
    for req in requests:
        # Post HITL card for this agent
        self._publish_hitl_card(
            room_id,
            agent_id=agent_id,
            question=req["question"],
            choices=req["choices"],
            context_data=req["context_data"],
            correlation_id=req["correlation_id"],
        )

# When user responds via attachment action:
from webex_use_case.hitl_helpers import resolve_agent_hitl

success = resolve_agent_hitl(
    session_id,
    agent_id,
    correlation_id,
    choice=inputs["hitl_choice"],
    steering=inputs.get("hitl_steering", ""),
)
# Continue conversation with resolved result
```

## Implementation Status

### ✅ Phase 1: Design + Tool Contract (Committed)

- System tool `request_human_input` with Pydantic Input
- `RequestHitlSignal` exception for control flow
- Architecture documentation

### ✅ Phase 2: Runtime Integration (IN PROGRESS - Ready to Commit)

- `HitlResolverRegistry` — Thread-safe global registry
- `_SystemToolHitlWrapper` — Signal catcher + marker emitter
- `inject_system_tools()` — Auto-inject into ManifestToolProvider
- `is_hitl_marker()` / `extract_hitl_metadata()` — Runtime detection helpers
- `AutoCtxAssembler` — Add session_id/agent_id/correlation_id fields
- `KernelDriver` — Propagate session/agent context to ctx
- `mas_session.py` — Track pending HITL agents in delegation state

### ✅ Phase 3: Webex Bot Helpers (Ready to Commit)

- `hitl_helpers.py` — Detection and resolution functions
- Integration pattern documented

### 🔄 Phase 4: Webex Bot UI (TODO - Next Session)

**Files to Modify**:
- `webex-use-case/src/webex_use_case/bot.py`

**Implementation**:
```python
def _handle_room_text(self, room_id, text):
    result = self.session.ask(text)
    
    # Check for pending HITL after ask
    pending = get_pending_hitl_for_session(result.session_id)
    for agent_id, requests in pending.items():
        for req in requests:
            self._publish_agent_hitl_card(
                room_id,
                agent_id,
                req["correlation_id"],
                req["question"],
                req["choices"],
                req["context_data"],
            )

def _handle_attachment_action(self, attachment_action):
    inputs = attachment_action.inputs
    if inputs.get("action_type") == "hitl_resolve":
        session_id = inputs["session_id"]
        agent_id = inputs["agent_id"]
        correlation_id = int(inputs["correlation_id"])
        choice = inputs["hitl_choice"]
        steering = inputs.get("hitl_steering", "")
        
        success = resolve_agent_hitl(
            session_id, agent_id, correlation_id, choice, steering
        )
        if success:
            # Resume conversation
            self._post_message(
                room_id,
                f"✅ Choice recorded: {choice}. Continuing..."
            )
```

## Testing Plan

1. **Unit Test**: `RequestHumanInputTool.execute()` raises signal
2. **Integration Test**: Wrapper catches signal and returns marker
3. **Registry Test**: Register/resolve cycle works
4. **Delegation Test**: finance-agent calls `request_human_input`, moderator detects pending
5. **Webex Test**: Bot posts HITL card, user clicks, resolution propagates

## Benefits of This Architecture

✅ **Distributed-ready**: HITL state propagates via side channel (registry)  
✅ **Non-blocking**: Other agents continue while one awaits user input  
✅ **Clean contract**: System tool, not app-local plugin  
✅ **Mealy-compatible**: No kernel modifications, uses existing egress flow  
✅ **Delegation-safe**: Pending HITL tracked in state, doesn't break delegation contract
