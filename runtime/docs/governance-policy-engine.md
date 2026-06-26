<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Governance Policy Engine — Plugin Specification

> **Module**: `mas.runtime.contracts.governance.policy_engine`  
> **Contract ID**: `governance_policy`  
> **Plugin ID**: `governance_policy_engine@v1`  
> **Phase**: SECURITY (priority 10)  
> **Status**: Implemented  

---

## 1. Overview

The Governance Policy Engine is a **unified declarative plugin** that generalises
all governance concerns — guardrails, human-in-the-loop (HITL), budget triggers,
content filters, circuit-breakers — into a single orthogonal model:

```
trigger  ×  evaluation  ×  action
```

This three-axis decomposition means:

- **Any trigger point** can use **any evaluation mode** and dispatch **any action**
- Adding a new trigger point does not require new action code
- Adding a new evaluation mode makes it available to all trigger points
- Adding a new action makes it available to all policies

The engine replaces ad-hoc governance implementations scattered across separate
plugins with a single, configurable, composable policy enforcement mechanism.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent/Overlay YAML                            │
│                                                                 │
│  governance:                                                    │
│    policies:                                                    │
│      - name: high-cost-approval                                 │
│        trigger: {on: tool_output, tool: fare_estimation, ...}   │
│        action: hitl                                             │
│        params: {auto_approve: true, timeout_s: 10}              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ parsed at load time
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              GovernancePolicyEngine                              │
│                                                                 │
│  ┌──────────┐    ┌────────────────┐    ┌──────────────┐        │
│  │  Trigger │───▶│  Condition     │───▶│  Action      │        │
│  │  Matcher │    │  Evaluator     │    │  Dispatcher  │        │
│  └──────────┘    └────────────────┘    └──────────────┘        │
│                                                                 │
│  Hooks:                                                         │
│    on_pre_tool_call   → tool_input triggers                     │
│    on_post_tool_call  → tool_output triggers                    │
│    on_post_llm_call   → llm_output + budget_threshold triggers  │
│    on_post_agent_communication → delegation_output triggers     │
│    on_governance_event → event (meta-policy) triggers           │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Hook Plane (L2)                               │
│                                                                 │
│  SECURITY phase (0-19): block, terminate, hitl                  │
│  → PolicyViolation raised = DENY gate                           │
│  → HITLRequest emitted = pause                                  │
│                                                                 │
│  TRANSFORMATION phase (20-79): modify                           │
│  → payload rewritten in-flight                                  │
│                                                                 │
│  OBSERVABILITY phase (80+): log                                 │
│  → governance_event emitted (fail-open)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Configuration Schema

### 3.1 Policy Definition

```yaml
governance:
  policies:
    - name: <string>           # Required. Unique policy identifier.
      enabled: <bool>          # Optional (default: true). Disable without removing.
      trigger:
        on: <trigger_point>    # Required. WHERE the policy fires.
        tool: <string>         # Optional (default: "*"). Tool name filter.
        condition: <string>    # Optional (default: ""). Condition expression.
        evaluation: <mode>     # Optional (default: "deterministic"). HOW to evaluate.
      action: <action>         # Required. WHAT to do when fired.
      params: <dict>           # Optional. Action-specific parameters.
```

### 3.2 Trigger Points (`on:`)

| Value | Hook | Description |
|-------|------|-------------|
| `tool_input` | `on_pre_tool_call` | Before a tool executes (arguments available) |
| `tool_output` | `on_post_tool_call` | After a tool returns (result available) |
| `llm_output` | `on_post_llm_call` | After LLM generates response |
| `delegation_output` | `on_post_agent_communication` | After inter-agent delegation returns |
| `budget_threshold` | `on_post_llm_call` | After LLM call, checks cumulative usage |
| `event` | `on_governance_event` | Meta-policy: fires on any governance event |

### 3.3 Tool Filter (`tool:`)

- `"*"` — matches all tools (default)
- `"fare_estimation"` — exact tool name match
- Only relevant for `tool_input` and `tool_output` triggers

### 3.4 Evaluation Modes (`evaluation:`)

| Mode | Cost | Guarantee | Use Case |
|------|------|-----------|----------|
| `deterministic` | Zero | Guaranteed (no LLM call) | Numeric thresholds, string matching, enum checks |
| `llm_judge` | 1 LLM call | Probabilistic | Content safety, semantic relevance, nuanced policies |

### 3.5 Condition Expression Language

For `deterministic` evaluation, conditions use a safe expression syntax:

```
<path> <operator> <literal>
```

**Paths**: Dotted attribute access into the data dict.

- `result.total_cost_usd` → `data["result"]["total_cost_usd"]`
- `arguments.destination` → `data["arguments"]["destination"]`
- `content` → `data["content"]`
- `usage.total_tokens` → `data["usage"]["total_tokens"]`

**Operators**: `>`, `<`, `>=`, `<=`, `==`, `!=`, `in`, `not in`, `contains`

**Literals**: Numbers (`500`, `3.14`), quoted strings (`"Paris"`), booleans (`True`/`False`), `None`

**Empty condition**: Always fires (unconditional trigger).

### 3.6 Actions

| Action | Behaviour | Phase | Blocking? |
|--------|-----------|-------|-----------|
| `block` | Raises `PolicyViolation` — DENY gate | SECURITY | Yes |
| `terminate` | Raises `PolicyViolation` with `terminal=True` — aborts agent | SECURITY | Yes |
| `hitl` | Emits `HITLRequest` event — runtime pauses for human review | SECURITY | Conditional |
| `log` | Emits `governance_policy` event — observability only | OBSERVABILITY | No |
| `modify` | Rewrites hook payload in-flight | TRANSFORMATION | No |

### 3.7 Action Parameters

#### `hitl` params

```yaml
params:
  auto_approve: true    # Auto-approve after timeout (default: false)
  timeout_s: 30.0       # Seconds to wait for human response (default: 30)
```

#### `modify` params

```yaml
params:
  set:                  # Overwrite fields
    result.approved: true
    result.capped_cost: 500
  remove:              # Delete fields
    - result.raw_pii
    - result.internal_notes
  append:              # Append to list fields
    result.annotations: "cost_capped_by_policy"
```

---

## 4. Data Flow

### 4.1 Hook Data Payloads

Each trigger point receives different data from the runtime:

**`tool_input` (on_pre_tool_call):**

```python
{
    "tool_name": "fare_estimation",
    "arguments": {"origin": "NYC", "destination": "Paris", "date": "2025-03-15"},
    # ... other tool call metadata
}
```

**`tool_output` (on_post_tool_call):**

```python
{
    "tool_name": "fare_estimation",
    "result": {"total_cost_usd": 750, "airline": "AF", "class": "business"},
    # ... execution metadata
}
```

**`llm_output` (on_post_llm_call):**

```python
{
    "content": "I recommend booking the Air France flight...",
    "usage": {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
    "model": "gpt-4o",
}
```

**`delegation_output` (on_post_agent_communication):**

```python
{
    "source_agent_id": "moderator",
    "target_agent_id": "concierge_agent",
    "message_type": "delegation",
    "result": {"itinerary": [...], "total_cost": 1200},
    "status": "success",
}
```

### 4.2 Evaluation Context

The condition evaluator operates on a normalized dict built from hook data:

- For `tool_output`: the data is wrapped so `result.*` paths work
- For `budget_threshold`: `cumulative.*` paths are available (from runtime context)
- Empty condition (`""`) always evaluates to `True` — unconditional trigger

### 4.3 Event Emission

Every policy evaluation emits a structured event:

```python
{
    "kind": "governance_policy",
    "policy_name": "high-cost-approval",
    "trigger_point": "tool_output",
    "evaluation_mode": "deterministic",
    "outcome": "fired",         # "fired" | "passed" | "error"
    "action_taken": "hitl",     # "" if passed
    "details": {
        "condition": "result.total_cost_usd > 500",
        "tool_filter": "fare_estimation",
    }
}
```

---

## 5. Integration with Runtime

### 5.1 Registration

```python
from mas.runtime.contracts.governance import GovernancePolicyEngine

# From YAML config
governance_config = agent_config.get("governance", {})
if governance_config.get("policies"):
    engine = GovernancePolicyEngine.from_config(governance_config)
    plugin_registry.register_plugin(engine, name="governance_policy_engine", priority=10)
```

### 5.2 LLM Judge Injection

```python
async def llm_judge(policy_name: str, condition: str, data: dict) -> bool:
    """Secondary LLM call to evaluate semantic conditions."""
    prompt = f"Policy '{policy_name}' condition: {condition}\nData: {data}\nDoes this violate the policy? Answer YES or NO."
    response = await llm_client.complete(prompt, model="gpt-4o-mini")
    return "YES" in response.content.upper()

engine.set_llm_judge(llm_judge)
```

### 5.3 HITL Handler

The runtime must register a HITL handler to intercept `hitl_request` events:

```python
class HITLHandler:
    """Intercepts HITL requests and pauses agent execution."""
    
    async def on_hitl_request(self, event: dict) -> bool:
        """Returns True to approve, False to deny."""
        if event.get("auto_approve"):
            await asyncio.sleep(event["timeout_s"])
            return True
        # ... present to human via UI/webhook ...
```

### 5.4 Overlay Composition

Policies can be layered via OASF overlays:

```yaml
# overlays/production-governance.yaml
spec:
  governance:
    policies:
      - name: cost-cap
        trigger: {on: tool_output, tool: "*", condition: "result.cost > 1000"}
        action: block
      - name: pii-filter
        trigger: {on: llm_output, condition: "", evaluation: llm_judge}
        action: modify
        params:
          set: {content: "[REDACTED]"}
```

Multiple overlays merge their policy lists additively.

---

## 6. Contract Taxonomy Position

```
GovernanceContract (L3)
├── BudgetContract        — resource accounting (tokens, cost, call-rate)
├── RoutingContract       — topology/edge policy
├── GovernancePolicyEngine — UNIFIED declarative policies (this plugin)
         ↑
         Generalises budget and routing into trigger × evaluation × action
```

Sandbox and TBAC governance contracts are documented and implemented in
`mas-lab-internal` only (not part of the OSS release).

The GovernancePolicyEngine is **complementary** to specialized governance contracts:

- BudgetContract provides fine-grained token accounting (counters, dimensions)
- GovernancePolicyEngine provides declarative threshold policies on top

A `budget_threshold` trigger can reference the cumulative usage from BudgetContract,
creating a layered governance stack.

---

## 7. Design Principles

### 7.1 Orthogonality

Each axis is independent:

- **Trigger** determines WHERE in the execution a policy evaluates
- **Evaluation** determines HOW the condition is checked
- **Action** determines WHAT happens when the condition fires

New capabilities on any axis compose with all existing values on the other axes.

### 7.2 Fail-Safe Defaults

- Empty condition = always fires (explicit, no silent pass-through)
- Missing LLM judge = policy does NOT fire (fail-safe: don't act without evaluation)
- Unknown evaluation mode = policy does NOT fire
- Parse error in condition = policy does NOT fire (logged as warning)

### 7.3 Zero Coupling

- Policies reference tools by name string, not by import
- No dependency on specific tool implementations
- No dependency on specific agent structure
- Works with any PluginRegistry-compatible runtime

### 7.4 Composable Governance

- Multiple policies on the same trigger point execute in declaration order
- First `block`/`terminate` action short-circuits (raises immediately)
- `log` and `modify` actions are non-blocking and compose
- Overlay YAML merges policy lists additively

---

## 8. Testing

### Unit Tests

```python
from mas.runtime.contracts.governance import (
    GovernancePolicyEngine, ConditionEvaluator, PolicyViolation
)

# Condition evaluator
assert ConditionEvaluator.evaluate("x > 5", {"x": 10}) == True
assert ConditionEvaluator.evaluate("x > 5", {"x": 3}) == False
assert ConditionEvaluator.evaluate("name == \"test\"", {"name": "test"}) == True
assert ConditionEvaluator.evaluate("items contains \"a\"", {"items": ["a", "b"]}) == True

# Policy engine
engine = GovernancePolicyEngine(policies=[{
    "name": "test",
    "trigger": {"on": "tool_output", "tool": "calc", "condition": "result.value > 100"},
    "action": "block",
}])

# Should raise
try:
    engine.on_post_tool_call({"tool_name": "calc", "result": {"value": 200}})
    assert False
except PolicyViolation:
    pass

# Should pass through
result = engine.on_post_tool_call({"tool_name": "calc", "result": {"value": 50}})
assert result == {"tool_name": "calc", "result": {"value": 50}}
```

### Integration Test Pattern

```yaml
# test-governance-experiment.yaml
experiment:
  name: governance-policy-integration
  scenarios:
    - id: cost-block
      overlay: overlays/strict-governance.yaml
      expected_outcome: agent_blocked
    - id: cost-allow
      overlay: overlays/permissive-governance.yaml
      expected_outcome: agent_completes
```

---

## 9. Performance Characteristics

| Evaluation Mode | Latency Added | Cost |
|----------------|---------------|------|
| `deterministic` | < 1ms (dict traversal + comparison) | Zero |
| `llm_judge` | 200-2000ms (secondary LLM call) | 1 API call per trigger |

- Policy matching: O(n) over declared policies per hook invocation
- Condition parsing: compiled regex, negligible overhead
- For high-frequency hooks (pre_tool_call on every tool), keep policies deterministic

---

## 10. Migration from Ad-Hoc Governance

### Before (scattered implementations)

```python
# In agent config
guardrails:
  max_cost: 500
  forbidden_destinations: ["Celestia", "Polaria"]
  
hitl:
  triggers:
    - post_concierge_result
  auto_approve: true
  timeout: 10
```

### After (unified policy model)

```yaml
governance:
  policies:
    - name: cost-cap
      trigger: {on: tool_output, tool: fare_estimation, condition: "result.total_cost_usd > 500"}
      action: block
    - name: forbidden-destination
      trigger: {on: tool_input, tool: book_flight, condition: "arguments.destination == \"Celestia\""}
      action: block
    - name: human-review
      trigger: {on: tool_output, tool: fare_estimation, condition: "result.total_cost_usd > 200"}
      action: hitl
      params: {auto_approve: true, timeout_s: 10}
```

---

## 11. Future Extensions

| Extension | Status | Notes |
|-----------|--------|-------|
| `regex` evaluation mode | Planned | Pattern matching on string fields |
| `schema` evaluation mode | Planned | JSON Schema validation on payload |
| Policy groups (AND/OR composition) | Planned | Compose multiple conditions |
| Priority ordering within trigger point | Planned | Control evaluation order |
| Async LLM judge | Planned | Non-blocking judge with callback |
| Policy metrics (Prometheus) | Planned | Count fires/passes per policy |
