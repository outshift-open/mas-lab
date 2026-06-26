<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# MAS Topology Schema Reference

Complete specification for multi-agent system topology definition files.

## Overview

A MAS topology defines:

- Agent configurations and relationships
- Communication patterns and protocols
- Governance policies
- Deployment settings
- System-level parameters

## Root Schema

```yaml
# topology.yaml
apiVersion: "mas.framework/v1"
kind: "MAS"
metadata:
  name: "my-mas"
  version: "1.0.0"
spec:
  # System description
  description: "Multi-agent search system"
  
  # Agent definitions
  agents:
    - name: "coordinator"
      agent_config: "agents/coordinator.yaml"
      replicas: 1
    
    - name: "searcher"
      agent_config: "agents/searcher.yaml"
      replicas: 3
  
  # Agent communication topology
  topology:
    connections:
      - from: "coordinator"
        to: "searcher"
        protocol: "agent-remote"  # Agent-to-Agent messaging
        latency_ms: 100
  
  # System-level policies
  policies:
    - name: "tool-allowlist"
      type: "governance"
      config:
        mode: "whitelist"
        tools:
          - "web_search"
          - "calculator"
  
  # Deployment configuration
  deployment:
    namespace: "production"
    replicas: 1
    resources:
      cpu: "2"
      memory: "4Gi"
```

## Metadata (`metadata`)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | ✅ | System identifier (alphanumeric, hyphens) |
| `version` | string | ✅ | Semantic version |
| `description` | string | ❌ | Human-readable description |

## Agent Specifications (`spec.agents[]`)

Define each agent in the system.

```yaml
agents:
  - name: "coordinator"
    agent_config: "agents/coordinator.yaml"
    replicas: 1
    env:
      ROLE: "coordinator"
    resources:
      cpu: "1"
      memory: "2Gi"
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | ✅ | Agent identifier |
| `agent_config` | string | ✅ | Path to agent.yaml manifest |
| `replicas` | int | ❌ | Number of instances (default: 1) |
| `env` | object | ❌ | Environment variables for this agent |
| `resources` | object | ❌ | CPU/memory constraints |

## Topology (`spec.topology`)

Define how agents communicate.

### Connection Types

```yaml
topology:
  connections:
    # Agent-to-Agent: Direct messaging
    - from: "searcher"
      to: "ranker"
      protocol: "agent-remote"
      config:
        message_queue: "rabbitmq"  # optional transport
        timeout_ms: 5000
    
    # HTTP/RPC: Function call style
    - from: "coordinator"
      to: "validator"
      protocol: "rpc"
      config:
        endpoint: "http://validator:8080"
        timeout_ms: 3000
    
    # Pub/Sub: Event streaming
    - from: "logger"
      to: "*"  # broadcast to all
      protocol: "pubsub"
      config:
        topic: "events"
```

| Connection Field | Type | Description |
| --- | --- | --- |
| `from` | string | Source agent name |
| `to` | string | Target agent (or `"*"` for broadcast) |
| `protocol` | string | `"agent-remote"` (Agent-to-Agent), `"rpc"`, `"pubsub"` |
| `config` | object | Protocol-specific settings |

---

## Governance Policies (`spec.policies[]`)

System-wide governance rules.

### Policy Types

#### Tool Allowlist

```yaml
policies:
  - name: "tool-allowlist"
    type: "governance"
    applies_to: ["searcher", "validator"]  # optional: specific agents
    config:
      mode: "whitelist"
      tools:
        - "web_search"
        - "calculator"
        - "database_query"
```

#### Timeout Policy

```yaml
policies:
  - name: "timeouts"
    type: "timeout"
    applies_to: "*"  # all agents
    config:
      default_timeout_ms: 30000
      per_tool_timeouts:
        web_search: 10000
        calculator: 1000
```

#### Rate Limiting

```yaml
policies:
  - name: "rate-limits"
    type: "rate-limit"
    applies_to: "*"
    config:
      llm_calls_per_second: 10
      tool_calls_per_minute: 100
      concurrent_requests: 5
```

#### Authentication/Authorization

```yaml
policies:
  - name: "authz"
    type: "authz"
    applies_to: "*"
    config:
      require_api_key: true
      api_key_env: "MAS_API_KEY"
```

---

## Deployment (`spec.deployment`)

Deployment and runtime configuration.

```yaml
deployment:
  namespace: "production"
  replicas: 3  # System replicas (separate from agent.replicas)
  
  # Resource constraints
  resources:
    cpu: "4"
    memory: "8Gi"
    gpu: "1"  # optional
  
  # Scaling policy
  autoscaling:
    enabled: true
    min_replicas: 1
    max_replicas: 10
    target_cpu_utilization: 70
  
  # Update strategy
  update_strategy: "rolling"  # or "recreate"
  
  # Monitoring
  monitoring:
    enabled: true
    metrics_port: 9090
    traces_endpoint: "http://jaeger:4317"
```

---

## Complete Example

```yaml
# topology.yaml — Multi-agent search system
apiVersion: "mas.framework/v1"
kind: "MAS"
metadata:
  name: "search-system"
  version: "1.0.0"
  description: "Distributed multi-agent search and ranking"

spec:
  # Agents
  agents:
    # Coordinator: orchestrates searches
    - name: "coordinator"
      agent_config: "agents/coordinator.yaml"
      replicas: 1
      resources:
        cpu: "1"
        memory: "2Gi"
    
    # Searchers: parallel web search
    - name: "searcher"
      agent_config: "agents/searcher.yaml"
      replicas: 3
      resources:
        cpu: "0.5"
        memory: "1Gi"
    
    # Ranker: rank search results
    - name: "ranker"
      agent_config: "agents/ranker.yaml"
      replicas: 2
      resources:
        cpu: "1"
        memory: "2Gi"
    
    # Validator: fact-check results
    - name: "validator"
      agent_config: "agents/validator.yaml"
      replicas: 1
      resources:
        cpu: "0.5"
        memory: "1Gi"
  
  # Communication topology
  topology:
    connections:
      # Coordinator → Searchers (parallel queries)
      - from: "coordinator"
        to: "searcher"
        protocol: "agent-remote"
        config:
          timeout_ms: 10000
      
      # Searchers → Ranker (results aggregation)
      - from: "searcher"
        to: "ranker"
        protocol: "agent-remote"
        config:
          timeout_ms: 5000
      
      # Ranker → Validator (validation)
      - from: "ranker"
        to: "validator"
        protocol: "rpc"
        config:
          endpoint: "http://validator:8080"
          timeout_ms: 3000
  
  # System policies
  policies:
    # Tool restrictions
    - name: "tool-allowlist"
      type: "governance"
      applies_to: "*"
      config:
        mode: "whitelist"
        tools:
          - "web_search"
          - "url_fetch"
          - "calculator"
    
    # Rate limiting
    - name: "rate-limits"
      type: "rate-limit"
      config:
        llm_calls_per_second: 50
        tool_calls_per_minute: 1000
    
    # Timeout policy
    - name: "timeouts"
      type: "timeout"
      config:
        default_timeout_ms: 30000
        per_agent_timeouts:
          searcher: 10000
          coordinator: 60000
  
  # Deployment
  deployment:
    namespace: "production"
    replicas: 1
    
    resources:
      cpu: "8"
      memory: "16Gi"
    
    autoscaling:
      enabled: true
      min_replicas: 1
      max_replicas: 5
      target_cpu_utilization: 75
    
    monitoring:
      enabled: true
      metrics_port: 9090
```

---

## Design Patterns

### Pipeline Topology

Sequential agent chain:

```
User → Coordinator → Searcher → Ranker → Response
```

```yaml
topology:
  connections:
    - from: "coordinator"
      to: "searcher"
      protocol: "agent-remote"
    - from: "searcher"
      to: "ranker"
      protocol: "agent-remote"
```

### Fan-Out Topology

Parallel execution:

```
         ┌─→ Searcher-1
         ├─→ Searcher-2
User → Coordinator
         └─→ Searcher-3
```

```yaml
agents:
  - name: "searcher"
    replicas: 3

topology:
  connections:
    - from: "coordinator"
      to: "searcher"
      protocol: "agent-remote"
```

### Mesh Topology

All-to-all communication:

```yaml
topology:
  connections:
    - from: "*"
      to: "*"
      protocol: "pubsub"
```

---

## Best Practices

1. **Replicate searchers, not coordinators**: Coordinator is typically singleton
2. **Set realistic timeouts**: Based on typical agent execution time
3. **Use policies for safety**: Allowlist tools, rate limit aggressively
4. **Monitor resource usage**: Set CPU/memory limits
5. **Start simple**: Begin with pipeline, add complexity as needed

For more:

- [Agent Manifest Schema](agent-manifest.md)
