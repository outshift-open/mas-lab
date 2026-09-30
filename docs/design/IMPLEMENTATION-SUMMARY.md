# Agent-Driven HITL Implementation Summary

## ✅ COMPLETED: Phases 1-3 of 4

### Phase 1: Design + Tool Contract (Commit 0d75d43)

**Files Created:**
- `runtime/src/mas/runtime/system_tools/__init__.py`
- `runtime/src/mas/runtime/system_tools/request_human_input.py`
- `runtime/src/mas/runtime/system_tools/signal.py`
- `docs/design/agent-driven-hitl.md`
- `docs/design/agent-driven-hitl-impl-plan.md`

**System Tool API:**
```python
request_human_input(
    question: str,
    question_type: "CONFIRM" | "FREE_FORM" | "MULTIPLE_CHOICE" | "MULTI_SELECT" | "FORM",
    choices: list[str],
    context_data: dict[str, Any]
) -> user's response
```

**Control Flow Signal:**
```python
raise RequestHitlSignal(
    question=args.question,
    question_type=qt,
    choices=args.choices,
    context_data=args.context_data,
)
```

### Phase 2: Runtime Integration (Commit a03bdec)

**Files Created:**
- `runtime/src/mas/runtime/boundary/hitl/registry.py` — Thread-safe HITL resolver registry

**Files Modified:**
- `runtime/src/mas/runtime/engine/manifest_tool_provider.py` — Auto-inject system tools
- `runtime/src/mas/runtime/engine/tool_dispatch.py` — HITL marker detection
- `runtime/src/mas/runtime/driver/mocks.py` — Add session/agent context fields
- `runtime/src/mas/runtime/driver/driver.py` — Propagate context to tools
- `ctl/src/mas/ctl/executor/mas_session.py` — Track pending HITL in delegation

**Architecture Components:**

1. **HitlResolverRegistry** (Thread-safe, global singleton)
   ```python
   registry.register(session_id, agent_id, correlation_id, question, ...)
   registry.resolve(session_id, agent_id, correlation_id, choice, steering)
   registry.get_pending_for_session(session_id) → dict[agent_id, list[requests]]
   registry.has_pending(session_id, agent_id=None) → bool
   ```

2. **_SystemToolHitlWrapper** (Signal catcher)
   ```python
   def on_execute_tool(...):
       try:
           return self._tool.execute(**arguments)
       except RequestHitlSignal as signal:
           registry.register(...)
           return {"__hitl_request__": True, ...}  # Marker for runtime
   ```

3. **HITL Marker Detection** (tool_dispatch.py)
   ```python
   is_hitl_marker(result) → bool
   extract_hitl_metadata(result) → dict | None
   ```

4. **Context Propagation**
   - `AutoCtxAssembler` now has `session_id`, `agent_id`, `correlation_id` fields
   - `KernelDriver` syncs these on every `UserInputReceived` ingress
   - System tools can access runtime context via `ctx` parameter

5. **Delegation HITL Tracking**
   - `mas_session.py::send()` checks `result.awaiting_hitl`
   - Queries registry: `registry.has_pending(session_id, agent_id)`
   - Tracks `pending_hitl_agents` set in delegation state
   - **Side-channel propagation** — delegation contract unchanged (still returns `str`)

### Phase 3: External HITL Client Helpers (Commit 6c2c23d4)

**Files Created:**
- Integration-owned `hitl_helpers.py` module (outside this repository)

**Helper Functions:**
```python
get_pending_hitl_for_session(session_id) → dict[agent_id, list[serialized_requests]]
resolve_agent_hitl(session_id, agent_id, correlation_id, choice, steering) → bool
has_pending_hitl(session_id, agent_id=None) → bool
clear_session_hitl(session_id)
```

**Integration Pattern:**
```python
# In an external chat client handler:
result = session.ask(text)
pending = get_pending_hitl_for_session(result.session_id)
for agent_id, requests in pending.items():
    for req in requests:
        self._publish_agent_hitl_card(room_id, agent_id, req)

# In an interactive UI action handler:
if action_type == "hitl_resolve":
    resolve_agent_hitl(session_id, agent_id, correlation_id, choice, steering)
```

### Phase 4: External Client UI (TODO - Next Session)

**Files to Modify:**
- The integration's client-specific UI adapter

**Implementation Tasks:**
1. Add `_publish_agent_hitl_prompt()` method
2. Hook `get_pending_hitl_for_session()` after each `ask()`
3. Hook `resolve_agent_hitl()` in the UI action handler
4. Map agent_id to the correct client identity for posting prompts
5. Test end-to-end: finance-agent calls → chat prompt → user responds → resolution

## Architecture Benefits

✅ **Distributed-ready**: HITL state propagates via global registry, not delegation return path  
✅ **Non-blocking**: Other agents continue while one awaits user input  
✅ **Clean contract**: System tool auto-injected, no manifest declaration needed  
✅ **Mealy-compatible**: No kernel modifications, uses existing tool execution flow  
✅ **Delegation-safe**: Side-channel propagation preserves delegation contract (`send()` still returns `str`)  
✅ **Thread-safe**: HitlResolverRegistry uses RLock for concurrent MAS execution  

## Testing Status

✅ All imports verified with PYTHONPATH  
✅ System tools module structure correct  
✅ Registry API tested  
✅ External integration helper imports successful
✅ No runtime modifications to Mealy kernel  
✅ Delegation contract unchanged  

## Example Flow

```python
# 1. Finance agent calls system tool
request_human_input(
    question="Approve 20% discount for Acme renewal?",
    question_type="CONFIRM",
    choices=["approve", "reject"],
    context_data={"account": "Acme Corp", "discount": "20%", "ceiling": "15%"}
)

# 2. Tool raises signal
raise RequestHitlSignal(...)

# 3. Wrapper catches signal and registers in global registry
registry.register(
    session_id="sess-123",
    agent_id="finance-agent",
    correlation_id=456,
    question="Approve 20% discount for Acme renewal?",
    ...
)

# 4. Returns marker to runtime
return {"__hitl_request__": True, "question": "...", ...}

# 5. Delegation detects pending HITL
if result.awaiting_hitl:
    if registry.has_pending(session_id, "finance-agent"):
        state["pending_hitl_agents"].add("finance-agent")

# 6. External client polls registry after ask()
pending = get_pending_hitl_for_session("sess-123")
# → {"finance-agent": [{"question": "...", "choices": [...], ...}]}

# 7. Client posts an interactive prompt to the conversation
self._publish_agent_hitl_card(room_id, "finance-agent", pending["finance-agent"][0])

# 8. User clicks "approve" button

# 9. Client receives the user's UI action
resolve_agent_hitl("sess-123", "finance-agent", 456, "approve", "")

# 10. Resolution propagates back to agent
# (callback mechanism to be implemented in Phase 4)
```

## Branches

- **mas-lab**: `feat/agent-hitl-runtime` (from `legacy/pre-v0.1`)
- **ioc-core-mas-lab**: `feat/library-verification-ci` (from current branch)

## Next Steps

1. **Phase 4**: Implement external client UI integration
    - Add support for posting HITL prompts
    - Add prompt builders for different question types
   - Test end-to-end flow

2. **Future**: Implement callback mechanism for resolution propagation
   - Registry callback support (currently stub)
   - Resume agent turn after resolution
   - Return user's choice as tool result

3. **Documentation**: Update user guide with system tools
   - How to use `request_human_input`
   - Example scenarios (approval gates, multi-choice, forms)
   - Best practices for HITL in multi-agent systems

## Compatibility Matrix

| Component | Status | Notes |
|-----------|--------|-------|
| Mealy Machine | ✅ | No kernel modifications |
| Delegation | ✅ | Contract unchanged, side-channel propagation |
| Thread Safety | ✅ | Registry uses RLock |
| Observability | ✅ | Compatible, no conflicts |
| Governance | ✅ | System tools don't interfere with governance plugins |
| Tool Contract | ✅ | Follows existing ToolContract pattern |
| Runtime Context | ✅ | Extended AutoCtxAssembler fields |

---

**Implementation Date**: 2026-08-28  
**Feature Branch**: `feat/agent-hitl-runtime`  
**Status**: ✅ Phases 1-3 Complete, Phase 4 TODO
