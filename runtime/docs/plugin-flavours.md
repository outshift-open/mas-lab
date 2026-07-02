<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Plugin Flavours: Environment-Based Implementation Selection

## Problem

Apps shouldn't know whether they're using local mocks or production services. Deployment environment (dev/staging/prod) should determine implementation, not app code.

**Anti-pattern (without flavours)**:
```python
# App explicitly chooses implementation
if os.getenv("ENV") == "prod":
    from mas.runtime.tool_server_http import ToolServerHttpClient
    planner = ToolServerTripPlannerTool(tool_server_url="http://prod-server")
else:
    # Tools are declared via manifest refs, e.g. samples:tools/calc.tool.yaml
    planner = LocalTripPlannerTool(data_file="local_data.json")
```

**Pattern (with flavours)**:
```python
# App requests capability, system selects implementation
from mas.runtime.plugin_flavours import get_plugin

planner = get_plugin("trip_planning", flavour="auto")
# Dev: LocalTripPlannerTool (auto-selected)
# Prod: ToolServerTripPlannerTool (auto-selected)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ App Code (flavour-agnostic)                                │
│   tool = get_plugin("trip_planning", flavour="auto")       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ PluginFlavourRegistry                                       │
│   Capability: "trip_planning"                               │
│   ├─ DEV     → LocalTripPlannerTool                         │
│   ├─ TEST    → LocalTripPlannerTool                         │
│   ├─ STAGING → ToolServerTripPlannerTool (staging URL)            │
│   └─ PROD    → ToolServerTripPlannerTool (prod URL)               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────┴──────────────┐
        │ Environment Detection       │
        │ 1. DEPLOYMENT_FLAVOUR       │
        │ 2. NODE_ENV                 │
        │ 3. Default (DEV)            │
        └─────────────────────────────┘
```

## Usage

### 1. Register Plugin Variants

```python
from mas.runtime.plugin_flavours import register_plugin, Flavour

# Dev variant (mock, no network)
register_plugin(
    capability="trip_planning",
    plugin_class=LocalTripPlannerTool,
    flavour=Flavour.DEV,
)

# Prod variant (real tool server)
register_plugin(
    capability="trip_planning",
    plugin_class=ToolServerTripPlannerTool,
    flavour=Flavour.PROD,
)
```

### 2. Request Plugin (App Code)

```python
from mas.runtime.plugin_flavours import get_plugin

# Auto-detect from environment
tool = get_plugin("trip_planning", flavour=None, data_file="data.json")

# Or explicit flavour
tool = get_plugin("trip_planning", flavour=Flavour.DEV, data_file="data.json")
```

### 3. Environment Configuration

```bash
# Dev mode (local mock)
DEPLOYMENT_FLAVOUR=dev python -m app

# Staging mode (staging tool server)
DEPLOYMENT_FLAVOUR=staging python -m app

# Prod mode (production tool server)
DEPLOYMENT_FLAVOUR=prod python -m app
```

## Flavour Detection

Checks in order:

1. **DEPLOYMENT_FLAVOUR** env var: `dev|test|staging|prod`
2. **NODE_ENV** env var (Node.js compatibility): `development|test|staging|production`
3. **Default**: `dev`

## Example: NOA Trip Consumer

See [library-samples/apps/trip-planner/mas.yaml](../../library-samples/apps/trip-planner/mas.yaml) for a complete example.

**App code (flavour-agnostic)**:
```python
# Register flavours
register_trip_planner_flavours()

# Get tool (auto-select based on env)
trip_planner = get_plugin("trip_planning", flavour=None, data_file=cities_path)

# Use tool (identical in dev/prod)
result = trip_planner.plan_trip(origin, destination, context)
```

**Dev run**:
```bash
DEPLOYMENT_FLAVOUR=dev python -m noa_trip_consumer.app_flavoured
# Uses LocalTripPlannerTool (mock data, no network)
```

**Prod run**:
```bash
DEPLOYMENT_FLAVOUR=prod python -m noa_trip_consumer.app_flavoured --tool-server-url http://localhost:9090
# Uses ToolServerTripPlannerTool (real tool server)
```

## Built-in Flavours

```python
class Flavour(Enum):
    DEV = "dev"          # Local mocks, fast, no network
    TEST = "test"        # Testing environment
    STAGING = "staging"  # Pre-production
    PROD = "prod"        # Production
```

## Fallback Strategy

If requested flavour not available, tries DEV as fallback:

```python
# Requested: prod
# Available: dev, test
# Result: Falls back to dev
tool = get_plugin("trip_planning", flavour=Flavour.PROD)  # Returns DEV variant
```

## Creating New Capabilities

```python
# 1. Define abstract capability
class DataStoreTool:
    def store(self, key, value): raise NotImplementedError
    def retrieve(self, key): raise NotImplementedError

# 2. Implement variants
class LocalDataStoreTool(DataStoreTool):
    """Dev: In-memory dict"""
    def __init__(self):
        self.data = {}
    
    def store(self, key, value):
        self.data[key] = value
    
    def retrieve(self, key):
        return self.data.get(key)

class RedisDataStoreTool(DataStoreTool):
    """Prod: Real Redis"""
    def __init__(self, redis_url):
        import redis
        self.redis = redis.from_url(redis_url)
    
    def store(self, key, value):
        self.redis.set(key, value)
    
    def retrieve(self, key):
        return self.redis.get(key)

# 3. Register flavours
register_plugin("data_store", LocalDataStoreTool, Flavour.DEV)
register_plugin("data_store", RedisDataStoreTool, Flavour.PROD)

# 4. Use in app (flavour-agnostic)
store = get_plugin("data_store", redis_url="redis://localhost")
store.store("key", "value")
```

## Observability as Deployment Concern

Before flavours, observability was mixed into app logic:

```python
# Old: Observability in app
class RatingAgent(ObservabilityMixin):
    def rate(self, response):
        self.emit_event("rating_start", {})  # Observability!
        rating = compute_rating(response)
        self.emit_event("rating_complete", rating)  # Observability!
        return rating
```

With flavours, observability is deployment concern:

```python
# New: App logic only
class RatingAgent:
    def rate(self, response):
        return compute_rating(response)  # Pure business logic

# Observability wrapper (prod flavour only)
class ObservableRatingAgent(RatingAgent):
    def rate(self, response):
        self.emit_event("rating_start")
        result = super().rate(response)
        self.emit_event("rating_complete", result)
        return result

# Register flavours
register_plugin("rating", RatingAgent, Flavour.DEV)
register_plugin("rating", ObservableRatingAgent, Flavour.PROD)
```

## Benefits

1. **App code unchanged** across environments
2. **Dev/test faster** (no network, use mocks)
3. **Prod uses real services** (tool-server, Redis, etc.)
4. **Deployment concerns separated** from business logic
5. **Similar to mixins** but runtime-selected
6. **Type-safe** (all variants implement same interface)

## Experiment Results

See [paper labs](../../docs/paper/index.md) for reproducible experiment validation.

**Experiment 04: Flavour System**:
```
✅ Flavour system selects implementation based on environment
✅ App code remains flavour-agnostic
✅ Dev uses LocalTripPlannerTool (no network)
✅ Prod uses ToolServerTripPlannerTool (real tool-server)
```

## Common Patterns

### Pattern 1: Data Source (Local vs Network)

```python
# Dev: Local file
register_plugin("data_source", LocalFileDataSource, Flavour.DEV)

# Prod: S3/Database
register_plugin("data_source", S3DataSource, Flavour.PROD)
```

### Pattern 2: LLM Provider (Mock vs Real)

```python
# Dev: Mock LLM (deterministic)
register_plugin("llm", MockLLMPlugin, Flavour.DEV)

# Prod: OpenAI/Anthropic
register_plugin("llm", RealLLMPlugin, Flavour.PROD)
```

### Pattern 3: Observability (No-op vs Full)

```python
# Dev: No-op (skip telemetry)
register_plugin("observability", NoOpObservabilityPlugin, Flavour.DEV)

# Prod: Full telemetry (Otel, Jaeger, etc.)
register_plugin("observability", FullObservabilityPlugin, Flavour.PROD)
```

## API Reference

### `register_plugin(capability, plugin_class, flavour)`

Register plugin implementation for capability + flavour.

**Args**:
- `capability` (str): Capability name (e.g., "trip_planning")
- `plugin_class` (Type): Plugin class to instantiate
- `flavour` (Flavour): Deployment flavour

### `get_plugin(capability, flavour=None, **kwargs)`

Get plugin instance for capability.

**Args**:
- `capability` (str): Capability name
- `flavour` (Flavour | None): Flavour (auto-detect if None)
- `**kwargs`: Arguments for plugin constructor

**Returns**: Plugin instance

**Raises**:
- `KeyError`: Capability not registered
- `ValueError`: No plugin for flavour

### `set_default_flavour(flavour)`

Set default flavour (overrides auto-detection).

**Args**:
- `flavour` (Flavour): Default flavour

## See Also

- [dev/contracts/mealy-hooks-and-closure.md](dev/contracts/mealy-hooks-and-closure.md): Mealy Σ reference
- [Paper labs](../../docs/paper/index.md): Reproducible Section 5 experiments
- [runtime/README.md](../runtime/README.md): Plugin overview
