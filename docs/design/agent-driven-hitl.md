# Agent-Driven HITL via System Tools

## Problem Statement

Currently, HITL (`hitl_on_tool`, `hitl_on_tool_result`) is triggered by governance policy, not by agent choice. This creates two problems:

1. **No agent-initiated user interaction**: An agent (e.g., finance_agent) cannot explicitly ask the user a question and wait for the answer within its own turn logic.

2. **Distributed MAS incompatibility**: The current HITL mechanism only works because everything runs in the same process:
   - `SessionController._drain_hitl()` uses `self.hitl_terminal` (local HitlTerminal)
   - In delegation (`mas_session.py::send()`), the sub-agent's `result.awaiting_hitl` is ignored
   - Only `result.text` is returned to the caller
   - In a distributed MAS, the delegating agent would never know a HITL is pending

## Architecture Goal

**Side-channel HITL**: An agent can request user input without blocking the entire MAS round.

- The sub-agent emits a HITL request
- The request propagates via a "side channel" (not the delegation return path)
- The user can respond asynchronously
- The agent's tool call completes with the user's response
- Other agents in the round can continue while one agent awaits user input

## Design

### 1. System Tool: `request_human_input`

A built-in tool (not app-local plugin) that agents can call explicitly:

```yaml
tools:
  - name: request_human_input
    description: Ask the user a question and wait for their response
    parameters:
      question: str          # The question to ask
      question_type: str     # CONFIRM | FREE_FORM | MULTIPLE_CHOICE
      choices: list[str]     # For MULTIPLE_CHOICE
      context_data: dict     # Contextual data for UI display
```

When called:
- Emits `EmitHitlRequest` via governance egress
- The runtime pauses this agent's turn (but not the whole MAS)
- Returns user's response as the tool result

### 2. Side-Channel HITL Resolver

Instead of blocking in `_drain_hitl()`:

```python
# Current (broken for distributed):
result = controller.run_turn(prompt)
if result.awaiting_hitl:
    # LOCAL resolution only
    resolve = self.hitl_terminal.resolve(...)
    result = controller.submit_hitl(resolve)
return result.text

# New (side-channel):
result = controller.run_turn(prompt)
if result.awaiting_hitl:
    # Register HITL request in shared resolver
    hitl_resolver.register(
        agent_id=agent_id,
        request=result.hitl_requests[-1],
        callback=lambda resolve: controller.submit_hitl(resolve)
    )
    # Return partial result; HITL resolved externally
    return result.text or "[awaiting user input]"
```

### 3. Delegation Protocol Update

The delegation return should include HITL state:

```python
@dataclass
class DelegationResult:
    text: str
    awaiting_hitl: bool
    hitl_request: HitlRequest | None
```

This allows:
- The caller (moderator) to know a sub-agent is blocked
- External systems (Webex bot) to detect and resolve pending HITL
- The resolution to flow back via `submit_hitl()` on the correct agent

### 4. Webex Bot Integration

The Webex bot becomes the HITL resolver:

```python
# In webex bot _handle_room_text:
result = session.ask(text)
if result.awaiting_hitl and result.hitl_request:
    # Post question via the correct agent bot
    agent_key = extract_agent_from_context(result.hitl_request)
    agent_bot = self._agent_identities[agent_key]
    agent_bot.post_adaptive_card(room_id, build_hitl_card(result.hitl_request))
    # Wait for user response via attachment action
    # (handled in _handle_attachment_action)

# In _handle_attachment_action:
choice = inputs["hitl_choice"]
steering = inputs.get("hitl_steering", "")
result = session.resolve_hitl(choice, steering)
# Post updated result
```

## Implementation Steps

1. ✅ Create feature branch `feat/agent-hitl-runtime` on mas-lab
2. Add system tool contract `RequestHumanInputTool` in runtime
3. Wire system tool into `ManifestToolProvider` or equivalent
4. Modify `mas_session.py::send()` to handle `awaiting_hitl` return
5. Add shared `HitlResolver` registry for cross-agent HITL
6. Update Webex bot to use side-channel resolution
7. Test: finance_agent calls `request_human_input` during delegation

## Benefits

- **Agent autonomy**: Agents choose when to ask users
- **Distributed-ready**: HITL state propagates via side channel
- **Non-blocking rounds**: Other agents continue while one waits for user
- **Clean contract**: System tool, not app-local governance plugin
