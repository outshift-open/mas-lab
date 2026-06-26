<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# mas-library-eval

Evaluation library for MAS Lab — quality metrics and LLM-as-judge scoring using **MCE** (metrics-computation-engine).

## Architecture

This library provides:

1. **Library code** (`mas.library.eval.*`): MCE integration, session entity construction, metric computation
2. **Pipeline steps** (`mas.library.eval.steps`): Evaluation steps for benchmark pipelines
3. **CLI component** (`mas.library.eval.cli`): Auto-registered `mas-lab eval` command

When installed, `mas-library-eval` automatically registers the `mas-lab eval` command via the `mas.lab.cli.components` entry point.

## Installation

```bash
# From workspace root
cd library-eval && uv pip install -e .

# Verify installation
mas-lab eval --list-metrics
```

The `mas-lab eval` command is automatically available after installation — no manual CLI registration needed.

## Dependencies

- **metrics-computation-engine** — MCE core (public package from telemetry-hub)
- **mce_metrics_plugin** — Quality metrics plugin (GoalSuccessRate, Groundedness, ResponseCompleteness, etc.)

## Package Structure

```
src/mas/library/eval/
├── __init__.py
├── mce/                       # MCE integration
│   └── __init__.py            # Core API: compute_session_metrics, build_session_from_trace, METRIC_REGISTRY
├── steps/                     # Pipeline steps
│   └── __init__.py            # EvalMceStep for benchmark pipelines
└── cli/                       # CLI component
    └── __init__.py            # EvalCliComponent (auto-registered as 'mas-lab eval')
```

## CLI Component Integration

This library uses the `mas-lab` CLI extension system. When installed, it automatically registers the `eval` command:

**Entry point** (`pyproject.toml`):

```toml
[project.entry-points."mas.lab.cli.components"]
eval = "mas.library.eval.cli:EvalCliComponent"
```

**Component class** (`mas.library.eval.cli`):

```python
class EvalCliComponent:
    def register(self, app: click.Group) -> str:
        """Register 'eval' command on mas-lab CLI."""
        app.add_command(eval_cmd, name="eval")
        return "eval"
```

After installation, the command is immediately available:

```bash
mas-lab eval --help
```

## MCE vs MCE v2

| Feature | MCE (this component) | MCE v2 (proprietary extension) |
|---------|------------------------|------------------------------|
| Package | `metrics-computation-engine` | (not shipped here) |
| Input | OTEL spans (jsonl) | Custom trace format |
| Metrics | Native + mce_metrics_plugin | mce.providers.native.metrics |
| LLM setup | `LLMJudgeConfig` + `Jury` | `LLMService` (patched) |
| API | `async compute(SessionEntity)` | `compute(resource_id, context)` |
| Status | ✅ Public, stable | ⚠️  Private, complex |

## Usage

### Standalone CLI

```bash
# Score a single trace
mas-lab eval path/to/events.jsonl --metric GoalSuccessRate --metric Groundedness

# Batch scoring over a benchmark output tree
mas-lab eval path/to/experiment/ --metric GoalSuccessRate --recursive
```

### In Benchmarks

```yaml
# experiment.yaml
pipeline:
  - step: run-mas
    # ... execution config
  - step: eval-mce
    metrics:
      - GoalSuccessRate
      - Groundedness
      - ResponseCompleteness
    model: azure/gpt-4o
    api_key_env: OPENAI_API_KEY
```

### Programmatic

```python
from mas.library.eval.mce import compute_session_metrics, build_session_entity_from_trace

# Load trace
session_entity = build_session_entity_from_trace("path/to/events.jsonl")

# Compute metrics
results = await compute_session_metrics(
    session=session_entity,
    metrics=["GoalSuccessRate", "Groundedness"],
    llm_config={
        "LLM_MODEL_NAME": "azure/gpt-4o",
        "LLM_BASE_MODEL_URL": "https://api.openai.com/v1",
        "LLM_API_KEY": os.environ["OPENAI_API_KEY"],
    },
)
```

## Migration from MCE v2

**Before (MCE v2, broken)**:

```python
from mas.library.eval.mce import install_openai_llm_service, compute_session_metrics
install_openai_llm_service(model_override="azure/gpt-4o")
results = compute_session_metrics(trace_path, ["goal_success_rate"])
```

**After (MCE, this component)**:

```python
from mas.library.eval.mce import compute_session_metrics, build_session_from_trace
session = build_session_from_trace(trace_path)
results = await compute_session_metrics(session, ["GoalSuccessRate"], llm_config)
```

## Metric Names

MCE uses **CamelCase** metric names (matching class names):

| MCE v2 (old) | MCE (new) |
|--------------|--------------|
| `goal_success_rate` | `GoalSuccessRate` |
| `groundedness` | `Groundedness` |
| `response_completeness` | `ResponseCompleteness` |
| `task_delegation` | (upstream span stub — not in OSS registry) |
| `answer_relevancy` | (via deepeval adapter) |

## Configuration

LLM config is provided via `LLMJudgeConfig`:

```python
from metrics_computation_engine.models.requests import LLMJudgeConfig

llm_config = LLMJudgeConfig(
    LLM_MODEL_NAME="azure/gpt-4o",
    LLM_BASE_MODEL_URL="https://api.openai.com/v1",
    LLM_API_KEY=os.environ["OPENAI_API_KEY"],
)
```

Or as a dict:

```python
llm_config = {
    "LLM_MODEL_NAME": "azure/gpt-4o",
    "LLM_BASE_MODEL_URL": "https://api.openai.com/v1",
    "LLM_API_KEY": os.environ["OPENAI_API_KEY"],
}
```

## See Also

- [MCE documentation](https://github.com/agntcy/telemetry-hub/tree/main/metrics_computation_engine)
- [mce_metrics_plugin](https://github.com/agntcy/telemetry-hub/tree/main/metrics_computation_engine/plugins/mce_metrics_plugin)
- [Tutorial: Output Quality Evaluation](../../docs/tutorial-evaluation.md)
