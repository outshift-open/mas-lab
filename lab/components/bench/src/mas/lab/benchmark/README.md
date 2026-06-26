<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Benchmark Framework - Reusable Components

**Composable primitives for agent evaluation.**

## Philosophy

This framework follows these principles:

1. **Declarative over imperative** - Configure via YAML/JSON, not code
2. **Incremental over monolithic** - Add runs without rerunning everything
3. **Composable over all-in-one** - Mix and match components
4. **Human-readable over optimized** - Folder names you can understand
5. **DataFrame-native over custom formats** - Leverage pandas/polars ecosystem

## Components

### 1. Dataset (`dataset.py`)

Loads and manipulates evaluation datasets.

```python
from mas.lab.benchmark import Dataset

# Load from JSON
dataset = Dataset.from_json("math_problems.json")

# Filter by category
arithmetic = dataset.filter(category="arithmetic")

# Iterate
for item in dataset:
    print(item.id, item.prompt)
```

**JSON Format:**
```json
{
  "name": "dataset_name",
  "version": "v1",
  "items": [
    {
      "id": "001",
      "prompt": "Question text",
      "category": "category_name",
      "expected_answer": "Answer",
      "metadata_key": "metadata_value"
    }
  ]
}
```

### 2. ResultStorage (`storage.py`)

Manages human-readable folder structure.

```python
from mas.lab.benchmark import ResultStorage, RunMetadata

storage = ResultStorage("./results")

# Generate run ID
run_id = storage.generate_run_id("cot", run_number=1)
# → "cot_run_001_20260218_143022"

# Save run
metadata = RunMetadata(
    dataset_name="math",
    item_id="001",
    run_id=run_id,
    pattern="cot",
    timestamp="2026-02-18T14:30:22",
    config={"model": "gpt-4"},
    success=True,
    latency_ms=1234.5
)

storage.save_run(
    dataset_name="math",
    item_id="001",
    run_id=run_id,
    metadata=metadata,
    events_file=Path("events.jsonl"),
    artifacts={"log": Path("agent.log")}
)

# List all runs
runs = storage.list_runs("math")
# → [("math", "001", "cot_run_001_20260218_143022"), ...]
```

**Folder Structure:**
```
results/
  {dataset_name}/
    {item_id}/
      {run_id}/
        metadata.json
        events.jsonl
        artifacts/
    consolidated.parquet
```

### 3. MultiRunOrchestrator (`runner.py`)

Coordinates N runs per item across patterns.

```python
from mas.lab.benchmark import MultiRunOrchestrator

orchestrator = MultiRunOrchestrator(
    storage=storage,
    n_runs=3,
    pause_between_runs=1.0
)

# Define agent factory
async def agent_factory(pattern_name, pattern_config):
    # Your agent creation logic
    return agent

# Run benchmark
summary = await orchestrator.run_dataset(
    dataset=dataset,
    patterns={
        "cot": {"manifest": "cot.yaml"},
        "react": {"manifest": "react.yaml"}
    },
    agent_factory=agent_factory
)
```

### 4. ResultAnalyzer (`analysis.py`)

Consolidates results into DataFrame.

```python
from mas.lab.benchmark import ResultAnalyzer

analyzer = ResultAnalyzer(storage)

# Consolidate all runs
df = analyzer.consolidate_results(
    dataset_name="math",
    include_events=True,  # Parse event logs
    cache=True            # Save as Parquet
)

# Compute statistics
stats = analyzer.compute_statistics(df)
#    pattern  latency_ms_mean  success_rate  mean_tokens
# 0  cot      1234.5           0.95          567
# 1  react    890.2            0.92          423

# Compare patterns
comparison = analyzer.compare_patterns(df, ["cot", "react"], "latency_ms")
```

**DataFrame Schema:**
```python
df.columns
# ['dataset_name', 'item_id', 'run_id', 'pattern',
#  'timestamp', 'success', 'latency_ms', 'error',
#  'total_tokens', 'prompt_tokens', 'completion_tokens',
#  'tool_calls', 'llm_calls',
#  'config_*']
```

### 5. Pipeline plots (`plotnine` / `plot` steps)

Paper figures use **`type: plotnine`** in `experiment.yaml` `application.post`.
Ad-hoc charts from step data use **`type: plot`** with **`config.spec`** (plot library).

See [PIPELINE_DESIGN.md](PIPELINE_DESIGN.md) and `labs/*/experiment.yaml` for examples.

## Complete Example

```python
import asyncio
from pathlib import Path
from mas.lab.benchmark import (
    Dataset, ResultStorage, MultiRunOrchestrator,
    ResultAnalyzer,
)

async def my_agent_factory(pattern_name, pattern_config):
    # Your agent creation logic
    pass

async def main():
    # 1. Load dataset
    dataset = Dataset.from_json("dataset.json")
    
    # 2. Setup storage
    storage = ResultStorage("./results")
    
    # 3. Run benchmark
    orchestrator = MultiRunOrchestrator(storage, n_runs=3)
    await orchestrator.run_dataset(
        dataset,
        patterns={"cot": {}, "react": {}},
        agent_factory=my_agent_factory
    )
    
    # 4. Analyze
    analyzer = ResultAnalyzer(storage)
    df = analyzer.consolidate_results(dataset.name)
    stats = analyzer.compute_statistics(df)
    print(stats)
    # Plots: declare plotnine / plot steps in experiment.yaml application.post

asyncio.run(main())
```

## Incremental Updates

### Add Items
```python
# Load existing dataset
dataset = Dataset.from_json("dataset.json")

# Add new items
dataset.items.append(DatasetItem(id="006", prompt="New question"))

# Save
dataset.to_json("dataset.json")

# Run benchmark (only new items executed)
await orchestrator.run_dataset(dataset, patterns, agent_factory)
```

### Add Runs
```python
# Increase n_runs
orchestrator = MultiRunOrchestrator(storage, n_runs=5)  # Was 3

# Run again - adds run_004, run_005 to existing items
await orchestrator.run_dataset(dataset, patterns, agent_factory)
```

### Add Patterns
```python
# Add new pattern
patterns = {
    "cot": {...},
    "react": {...},
    "planner": {...}  # NEW
}

# Run again - only planner executed on all items
await orchestrator.run_dataset(dataset, patterns, agent_factory)
```

### Regenerate Plots
```python
# Re-run pipeline post steps only (content-addressed trace cache skips LLM calls)
# mas-lab benchmark run experiment.yaml --force-post
```

## Advanced Usage

### Custom Metrics

Extend `ResultAnalyzer._extract_event_metrics()`:

```python
def _extract_event_metrics(self, events_file: Path) -> Dict[str, Any]:
    metrics = super()._extract_event_metrics(events_file)
    
    # Add custom metrics
    metrics["my_custom_metric"] = ...
    
    return metrics
```

### Custom Plots

Add a `plotnine` step in `application.post` or a plot-library YAML under
`pipeline/steps/plot_library/`. See `labs/design-space.lab/01-design-patterns/experiment.yaml`.

### Parallel Execution

```python
# Run patterns in parallel
import asyncio

async def run_pattern(pattern_name, pattern_config):
    await orchestrator.run_dataset(
        dataset,
        patterns={pattern_name: pattern_config},
        agent_factory=agent_factory
    )

await asyncio.gather(
    run_pattern("cot", {...}),
    run_pattern("react", {...}),
)
```

## Dependencies

```bash
pip install pandas pyarrow plotnine pyyaml
```

## Testing

```bash
cd mas-lab
pytest tests/benchmark/
```

## Contributing

When adding new components:

1. Follow existing patterns (DataClass for data, Class for behavior)
2. Add docstrings with examples
3. Write tests in `tests/benchmark/`
4. Update this documentation
