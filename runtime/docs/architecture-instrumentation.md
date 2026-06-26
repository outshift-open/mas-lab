<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Architecture & Instrumentation Guide

## Question 1: Main Loop, Framework Integration, and Automatic Instrumentation

### Do We Replace or Wrap Framework Main Loops?

**Short answer**: We **wrap**, not replace. The runtime uses "Boundary Interception" pattern.

### Framework-Specific Integration

Each framework provides its own main loop and execution model:

| Framework | Main Loop | Interception Method | Code Reference |
|-----------|-----------|---------------------|----------------|
| **LangChain** | `AgentExecutor._call()` | Callback system | [real_langchain_modern.py](../paper/code/real_langchain_modern.py) |
| **LangGraph** | State machine transitions | Node injection | [real_langgraph_integration.py](../paper/code/real_langgraph_integration.py) |
| **AutoGen** | `UserProxyAgent.initiate_chat()` | Function decorators | [real_autogen_integration.py](../paper/code/real_autogen_integration.py) |
| **LlamaIndex** | Query engine execution | Tool wrapping + event bus | [real_llamaindex_integration.py](../paper/code/real_llamaindex_integration.py) |
| **agent-remote SDK** | `AgentExecutor.execute()` | Hook plane integration | See below |

### Do We Have Our Own Main Loop Plugin?

**No, and by design**. The runtime *deliberately* does not provide its own main loop because:

1. **Framework Native**: Developers invest in a framework's abstractions (LangChain chains, LangGraph graphs, AutoGen conversations). Forcing a new main loop breaks that investment.

2. **Boundary Enforcement**: Our value proposition is *adding* governance/observability *without* rewriting agent logic. If we provided a main loop, it would be "yet another framework."

3. **Mealy Machine Model**: The runtime *imposes* a Mealy-like control structure via hooks, not by replacing the loop. The framework's loop becomes the state machine's "transition function."

### How to Automatically Instrument Existing Apps?

Three approaches, ordered by intrusiveness:

#### Approach 1: Import Hook (Automatic, Zero Code Changes)

```python
# auto_instrument.py
import sys
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec

class RuntimeInstrumenter(MetaPathFinder):
    """Automatically wraps framework imports with governance."""
    
    def find_spec(self, fullname, path, target=None):
        # Intercept langchain/langgraph/autogen imports
        if fullname.startswith(('langchain', 'langgraph', 'autogen', 'llama_index')):
            # Return custom loader that wraps classes
            return ModuleSpec(fullname, RuntimeLoader(), is_package=False)
        return None

class RuntimeLoader(Loader):
    def exec_module(self, module):
        # Dynamically wrap key classes with governance hooks
        if hasattr(module, 'AgentExecutor'):
            original_call = module.AgentExecutor._call
            module.AgentExecutor._call = lambda self, *args, **kwargs: \
                runtime_wrapper(original_call, self, *args, **kwargs)

# Usage (single line in user's code)
sys.meta_path.insert(0, RuntimeInstrumenter())
# Now all langchain imports are auto-instrumented
```

**Pros**: Zero code changes to existing apps  
**Cons**: Fragile (depends on internal APIs), hard to debug  
**When to use**: Legacy apps you can't modify

#### Approach 2: Monkey Patching (Explicit, Minimal Changes)

```python
# instrument_langchain.py
from langchain.agents import AgentExecutor
from mas.runtime import PluginRegistry

def patch_langchain_with_governance(registry: PluginRegistry):
    """Monkey-patch LangChain AgentExecutor with runtime hooks."""
    original_call = AgentExecutor._call
    
    def governed_call(self, inputs, run_manager=None):
        # Pre-execution hooks
        registry.execute_hooks("pre_execution", inputs)
        
        # Original agent logic
        result = original_call(self, inputs, run_manager)
        
        # Post-execution hooks
        registry.execute_hooks("post_execution", result)
        
        return result
    
    AgentExecutor._call = governed_call

# Usage in existing app
from mas.runtime import PluginRegistry
registry = PluginRegistry([MyGovernancePlugin(), MyAuditPlugin()])
patch_langchain_with_governance(registry)
# Existing app code runs unchanged below
```

**Pros**: Explicit, works with existing codebases  
**Cons**: Requires identifying the right method to patch  
**When to use**: Production apps where you control initialization

#### Approach 3: Wrapper Classes (Recommended, Cleanest)

```python
# governed_agent.py
from mas.runtime import PluginRegistry
from langchain.agents import AgentExecutor

class GovernedAgentExecutor(AgentExecutor):
    """LangChain AgentExecutor with built-in governance."""
    
    def __init__(self, *args, plugins=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = PluginRegistry(plugins or [])
    
    def _call(self, inputs, run_manager=None):
        # Pre-execution hooks
        self.registry.execute_hooks("pre_execution", inputs)
        
        # Original agent logic
        result = super()._call(inputs, run_manager)
        
        # Post-execution hooks
        self.registry.execute_hooks("post_execution", result)
        
        return result

# Usage (replace one line in existing app)
# OLD: agent = AgentExecutor(...)
# NEW: agent = GovernedAgentExecutor(..., plugins=[MyGovernancePlugin()])
```

**Pros**: Clean abstraction, testable, framework-idiomatic  
**Cons**: Requires changing agent instantiation  
**When to use**: New development or refactoring existing apps

### Summary Table: Integration Methods

| Method | Code Changes | Robustness | Maintenance | Use Case |
|--------|-------------|------------|-------------|----------|
| Import Hook | 1 line | Low | High | Legacy codebases |
| Monkey Patching | 2-5 lines | Medium | Medium | Production with init control |
| Wrapper Classes | 1 line change | High | Low | New development |
| Native Callbacks | Framework-specific | High | Low | LangChain, LlamaIndex |

---

## Question 2: agent-remote SDK, Main Loop, and Tool Calling

### agent-remote SDK as Main Loop Provider

**Yes**, the agent-remote SDK (`agent-remote-sdk-py`) provides a production-grade main loop via `AgentExecutor`:

```python
# aether-agents reference (from workspace)
from agent_remote_sdk.server.agent_execution import AgentExecutor
from agent_remote_sdk.server.events import EventQueue

class MyAgent(AgentExecutor):
    async def execute(self, task, context):
        # Your agent logic runs inside agent-remote's main loop
        # agent-remote handles:
        # - Message routing (agent-to-agent)
        # - Event streaming
        # - Task lifecycle management
        pass
```

**What agent-remote SDK Provides Beyond Main Loop:**

1. **Agent-to-Agent Communication** (`AetherAgentRemoteClient`):
   - Message routing across network
   - Streaming responses
   - Correlation tracking

2. **Agent Lifecycle Management**:
   - Task queuing and scheduling
   - Capability registration (`AgentSkills`, `AgentCard`)
   - Health checks and status reporting

3. **Event System** (`EventQueue`):
   - Structured event emission
   - Observers/subscribers pattern
   - Telemetry integration

4. **Types and Validation**:
   - `AgentCapabilities`, `AgentCard` schemas
   - Request/response validation
   - Error taxonomy

### Why LlamaIndex for Tool Calling?

**LlamaIndex is used for two reasons:**

1. **Tool Infrastructure** (`FunctionTool`, `BaseTool`):
   - Schema definition (Pydantic-based)
   - Automatic OpenAPI spec generation
   - Argument validation
   - Error handling

2. **tool-server Integration** (`BasicToolServerClient`, `ToolServerToolSpec`):
   - Native support for Model Context Protocol
   - Tool discovery from tool servers
   - Automatic tool wrapping

**From aether-agents codebase:**

```python
# aether-agents/aether-agents-impact-assessment/tool_utils.py
from llama_index.core.tools import FunctionTool
from llama_index.tools.tool_server import BasicToolServerClient, ToolServerToolSpec

# LlamaIndex provides unified interface for:
# 1. Native Python functions (via FunctionTool)
# 2. tool-server remote tools (via ToolServerToolSpec)
# 3. Custom BaseTool implementations

def get_tools_for_tenant(agent_remote_client, tool_server_client):
    # Native tool (direct function)
    query_tool = FunctionTool.from_defaults(
        fn=lambda q: agent_remote_client.send_message("aether_ndm_query", data={"query": q}),
        name="query_ndm_database",
        description="Query the NDM database"
    )
    
    # tool servers (remote)
    tool_server_spec = ToolServerToolSpec(tool_server_client)
    tool_server_tools = tool_server_spec.to_tool_list()
    
    return [query_tool] + tool_server_tools
```

**Our Runtime Alternative:**

We *could* reimplement this with our own tool calling abstraction, but LlamaIndex already provides:

- Battle-tested tool schema validation
- tool-server client implementation
- Extensive tool library ecosystem

**Pragmatic choice**: Use LlamaIndex for tool calling, wrap it with our governance hooks.

### tool-server vs Native Tool Calling

| Aspect | Native (Python Functions) | tool-server (Remote Tools) |
|--------|--------------------------|-------------------|
| **Implementation** | `FunctionTool.from_defaults(fn=my_func)` | `BasicToolServerClient`, `ToolServerToolSpec` |
| **Location** | In-process | Remote server (HTTP/SSE) |
| **Discovery** | Static registration | Dynamic via tool server |
| **Schema** | Pydantic models | tool-server tool schema |
| **Governance** | Tool Contract hooks | Tool Contract hooks (same) |
| **Use Case** | Simple utilities | Enterprise services, external APIs |

**Both are governed the same way** via our Tool Contract hooks.

### Creating LlamaIndex Tool Calling Plugin

See `mas-runtime/src/mas/runtime/llamaindex_tools_plugin.py` (created below).

---

## Question 3: Mealy Machine Implementation

### Why No Explicit Mealy Machine Class?

**The runtime *is* a Mealy machine, but it's implicit in the architecture:**

| Mealy Component | Implementation |
|-----------------|----------------|
| **States (S)** | Agent execution state (`AgentState` enum) |
| **Input Alphabet (I)** | Messages, tool results, LLM responses |
| **Output Alphabet (O)** | Tool calls, agent responses, control signals |
| **Transition Function (δ)** | Framework main loop + plugin hooks |
| **Output Function (λ)** | Plugin chain execution |

**Why implicit vs explicit class?**

1. **Framework Diversity**: Each framework has different state representations. A unified class would need to abstract over LangChain's `AgentExecutor`, LangGraph's `StateGraph`, AutoGen's conversation state, etc.

2. **Performance**: Adding a state machine layer on top of existing framework state machines would be redundant overhead.

3. **Validation-Focused**: We only need Mealy properties for *validation* (deterministic governance), not for *execution*. The runtime enforces Mealy constraints via contract invariants.

**However**, an explicit `MealyMachine` class is valuable for:

- Formal verification
- Trace validation
- Documentation
- Testing

See `mas-runtime/src/mas/runtime/mealy_machine.py` (created below) for the reference implementation.

### When to Use Explicit vs Implicit Mealy Model

**Use Explicit MealyMachine class:**

- Trace validation in CI/CD
- Formal verification of governance policies
- Property-based testing
- Academic/research contexts

**Use Implicit model (existing runtime):**

- Production deployments
- Performance-critical paths
- Integration with diverse frameworks
- Operational governance

Both models provide the same guarantees; the explicit class makes properties *testable*.

---

## Summary: Architectural Choices

| Choice | Rationale |
|--------|-----------|
| **Wrap, not replace** | Preserve framework investment, avoid lock-in |
| **agent-remote SDK for coordination** | Production-tested MAS communication layer |
| **LlamaIndex for tool calling** | Battle-tested infrastructure, tool-server support |
| **Implicit Mealy machine** | Performance, framework diversity |
| **Explicit Mealy class** | Validation, formal verification |

The runtime architecture separates:

- **Execution substrate** (frameworks provide main loop)
- **Coordination protocol** (agent-remote SDK for MAS)
- **Tool infrastructure** (LlamaIndex for calling)
- **Governance layer** (our plugins enforce contracts)

This separation enables **horizontal composition**: add governance/observability *across* frameworks without vertical integration into any single framework's core.
