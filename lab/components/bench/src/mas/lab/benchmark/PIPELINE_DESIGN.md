<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Evaluation Pipeline System - Design Document

## Overview

Transform the benchmark framework into a declarative pipeline system with automatic dependency tracking, similar to Home Assistant configuration syntax.

## Problem Statement

**Current State:**
- Evaluation config is flat (eval_config.yaml)
- No dependency tracking between steps
- Manual orchestration of dataset → runs → analysis → plots
- Changes to dataset require manual decisions about what to rerun

**Desired State:**
- Declarative pipeline definition with explicit/implicit dependencies
- Automatic change detection (dataset modified → rerun affected steps)
- Composable: split config into files or keep in single file
- All results in structured output/ folder (logs/, data/, plots/)

## Architecture

### 1. Pipeline Concept

A pipeline is a DAG (Directed Acyclic Graph) of **steps**:

```yaml
# evaluation.yaml (root)
pipeline:
  name: "design-patterns-eval"
  version: "v1"
  
  steps:
    - name: "dataset"
      type: "dataset"
      config: !include datasets/math_reasoning.yaml
      
    - name: "run_cot"
      type: "experiment"
      depends_on: ["dataset"]
      config: !include experiments/cot.yaml
      
    - name: "run_react"
      type: "experiment"
      depends_on: ["dataset"]
      config: !include experiments/react.yaml
      
    - name: "consolidate"
      type: "analysis"
      depends_on: ["run_cot", "run_react"]
      config:
        include_events: true
        cache: true
      
    - name: "plot_latency"
      type: "plot"
      depends_on: ["consolidate"]
      config: !include plots/latency_distribution.yaml
      
    - name: "plot_comparison"
      type: "plot"
      depends_on: ["consolidate"]
      config: !include plots/pattern_comparison.yaml

  output:
    base_dir: "./output"
    structure:
      logs: "logs/{step_name}"
      data: "data/{step_name}"
      plots: "plots"
```

### 2. Dependency Types

**Explicit Dependencies** (via `depends_on`):
```yaml
steps:
  - name: "consolidate"
    depends_on: ["run_cot", "run_react"]  # Explicit
```

**Implicit Dependencies** (via data references):
```yaml
steps:
  - name: "run_cot"
    config:
      dataset: "@dataset.output"  # Implicit: depends on dataset step
      
  - name: "plot_latency"
    config:
      data_source: "@consolidate.dataframe"  # Implicit: depends on consolidate
```

**Dependency Resolution** uses both for complete DAG.

### 3. Step Types

| Type | Purpose | Outputs | Example |
|------|---------|---------|---------|
| `dataset` | Load/filter dataset | `output`: Dataset JSON | Load math problems |
| `experiment` | Run N trials | `logs/`, `data/`, `metadata.json` | Execute CoT pattern |
| `analysis` | Consolidate results | `dataframe`: parquet file | Compute statistics |
| `plot` | Generate visualization | `plots/*.svg` | Latency distribution |
| `metric` | Compute custom metric | `metrics.json` | LLM-as-judge scores |

### 4. Change Detection & Caching

Each step produces a **fingerprint** (hash of inputs + config):

```python
def compute_fingerprint(step: PipelineStep) -> str:
    """Hash of step config + dependency outputs."""
    inputs = {
        "config": step.config,
        "dependencies": {
            dep: get_step_output_hash(dep)
            for dep in step.depends_on
        }
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
```

**Cache structure:**
```
output/
  .cache/
    dataset.fingerprint          # Hash of dataset config
    run_cot.fingerprint          # Hash of cot config + dataset output
    consolidate.fingerprint      # Hash of analysis config + experiment outputs
  data/
    dataset/
      math_reasoning.json
    run_cot/
      001/run_001_.../ metadata.json, events.jsonl
    run_react/
      ...
    consolidate/
      consolidated.parquet
  plots/
    latency_distribution.svg
    pattern_comparison.svg
  logs/
    dataset.log
    run_cot.log
    ...
```

**Rerun logic:**
```python
def should_rerun(step: PipelineStep) -> bool:
    """Returns True if step needs rerun."""
    current_fingerprint = compute_fingerprint(step)
    cached_fingerprint = load_cached_fingerprint(step.name)
    
    if cached_fingerprint is None:
        return True  # Never run before
    
    if current_fingerprint != cached_fingerprint:
        return True  # Config or dependencies changed
    
    if not step.outputs_exist():
        return True  # Outputs deleted/missing
    
    return False
```

### 5. File Organization

**Option A: Monolithic (single file)**
```yaml
# evaluation.yaml
pipeline:
  name: "eval"
  steps:
    - name: "dataset"
      type: "dataset"
      config:
        path: "./datasets/math.json"
        
    - name: "run_cot"
      type: "experiment"
      depends_on: ["dataset"]
      config:
        manifest: "./manifests/cot.yaml"
        n_runs: 3
        
    # ... all steps inline
```

**Option B: Split by Section (Home Assistant style)**
```
evaluations/
  design-patterns-eval/
    evaluation.yaml           # Root config (imports only)
    datasets/
      math_reasoning.yaml     # Dataset config
    experiments/
      cot.yaml                # Experiment config
      react.yaml
    analysis/
      consolidate.yaml        # Analysis config
    plots/
      latency_distribution.yaml
      pattern_comparison.yaml
    output/                   # Generated
```

`evaluation.yaml`:
```yaml
pipeline:
  name: "design-patterns-eval"
  
  steps:
    - name: "dataset"
      type: "dataset"
      config: !include datasets/math_reasoning.yaml
      
    - name: "run_cot"
      type: "experiment"
      depends_on: ["dataset"]
      config: !include experiments/cot.yaml
```

**Option C: One File Per Step**
```
evaluations/
  design-patterns-eval/
    evaluation.yaml           # Root: only step list + dependencies
    steps/
      dataset.yaml
      run_cot.yaml
      run_react.yaml
      consolidate.yaml
      plot_latency.yaml
      plot_comparison.yaml
```

`evaluation.yaml`:
```yaml
pipeline:
  name: "design-patterns-eval"
  
  steps:
    - !include steps/dataset.yaml
    - !include steps/run_cot.yaml
    - !include steps/run_react.yaml
    - !include steps/consolidate.yaml
    - !include steps/plot_latency.yaml
    - !include steps/plot_comparison.yaml
```

`steps/run_cot.yaml`:
```yaml
name: "run_cot"
type: "experiment"
depends_on: ["dataset"]
config:
  manifest: "./manifests/cot.yaml"
  n_runs: 3
  timeout: 60
```

### 6. Python API

```python
from mas.lab.benchmark.pipeline import (
    Pipeline,
    PipelineExecutor,
    PipelineStep
)

# Load pipeline
pipeline = Pipeline.from_yaml("evaluation.yaml")

# Execute with automatic dependency resolution
executor = PipelineExecutor(pipeline)
results = await executor.run(
    force_rerun=False,        # Respect cache
    steps=None,               # Run all steps
    dry_run=False             # Actually execute
)

# Selective rerun (when dataset changes)
results = await executor.run(
    force_rerun=["dataset"],  # Force dataset step
    # Automatically reruns: run_cot, run_react, consolidate, plots
)

# Dry run (show what would run)
plan = await executor.run(dry_run=True)
print(plan.execution_order)  # ["dataset", "run_cot", "run_react", "consolidate", ...]
print(plan.steps_to_rerun)   # ["dataset", "run_cot", "run_react"]
```

### 7. Step Implementations

**Dataset Step:**
```python
class DatasetStep(PipelineStep):
    type = "dataset"
    
    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        config = self.config
        dataset = Dataset.from_json(config["path"])
        
        if "filter" in config:
            dataset = dataset.filter(**config["filter"])
        
        output_path = ctx.output_dir / "data" / self.name / f"{dataset.name}.json"
        dataset.to_json(output_path)
        
        return StepOutput(
            data={"dataset": dataset},
            files=[output_path],
            metadata={"name": dataset.name, "count": len(dataset)}
        )
```

**Experiment Step:**
```python
class ExperimentStep(PipelineStep):
    type = "experiment"
    
    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        # Get dataset from dependencies
        dataset = ctx.get_dependency_output("dataset")["dataset"]
        
        # Setup storage
        storage = ResultStorage(ctx.output_dir / "data" / self.name)
        
        # Run orchestrator
        orchestrator = MultiRunOrchestrator(
            storage=storage,
            n_runs=self.config["n_runs"]
        )
        
        manifest_path = Path(self.config["manifest"])
        summary = await orchestrator.run_dataset(
            dataset=dataset,
            patterns={self.name: {"manifest": manifest_path}},
            agent_factory=lambda pn, pc: create_agent(pn, pc)
        )
        
        return StepOutput(
            data={"summary": summary},
            files=list(storage.base_dir.rglob("*.json")),
            metadata=summary
        )
```

**Analysis Step:**
```python
class AnalysisStep(PipelineStep):
    type = "analysis"
    
    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        # Collect experiment outputs
        experiment_steps = [dep for dep in self.depends_on if dep.startswith("run_")]
        
        storage_dirs = [
            ctx.output_dir / "data" / step_name
            for step_name in experiment_steps
        ]
        
        # Consolidate
        analyzer = ResultAnalyzer(storage_dirs[0])  # Uses all subdirs
        df = analyzer.consolidate_results(
            dataset_name=ctx.pipeline.get_step("dataset").config["name"],
            include_events=self.config.get("include_events", True)
        )
        
        # Save
        output_path = ctx.output_dir / "data" / self.name / "consolidated.parquet"
        df.to_parquet(output_path)
        
        return StepOutput(
            data={"dataframe": df},
            files=[output_path],
            metadata={"rows": len(df), "columns": list(df.columns)}
        )
```

**Plot Step:** use ``config.spec`` (plot library) or ``type: plotnine`` for paper figures. Legacy ``config.type`` / ``ResultVisualizer`` paths are removed.

```python
class PlotStep(PipelineStep):
    type = "plot"

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        spec_name = self.config["spec"]  # required
        ...
```

### 8. CLI Interface

```bash
# Run full pipeline
mas-lab pipeline run evaluation.yaml

# Dry run (show execution plan)
mas-lab pipeline run evaluation.yaml --dry-run

# Force specific steps
mas-lab pipeline run evaluation.yaml --force dataset,run_cot

# Run only specific steps (+ dependencies)
mas-lab pipeline run evaluation.yaml --only plot_latency

# Show pipeline structure
mas-lab pipeline show evaluation.yaml

# Validate pipeline config
mas-lab pipeline validate evaluation.yaml

# Clean outputs
mas-lab pipeline clean evaluation.yaml
```

### 9. Integration with Existing mas-lab

**Directory structure:**
```
mas-lab/
  evaluations/                    # NEW: Declarative evaluations
    example-design-patterns/
      evaluation.yaml
      datasets/
        math_reasoning.yaml
      experiments/
        cot.yaml
        react.yaml
      plots/
        latency_distribution.yaml
      output/                     # Generated
        .cache/
        data/
        plots/
        logs/
    
  src/mas/lab/
    benchmark/
      __init__.py
      dataset.py                  # Existing
      storage.py                  # Existing
      runner.py                   # Existing
      analysis.py                 # Existing
      visualization.py            # Existing
      pipeline/                   # NEW
        __init__.py
        pipeline.py               # Pipeline, PipelineStep
        executor.py               # PipelineExecutor
        steps/                    # Step implementations
          __init__.py
          dataset.py
          experiment.py
          analysis.py
          plot.py
          collect_metrics.py
          eval_mce.py
        resolver.py               # Dependency resolver
        cache.py                  # Fingerprinting & caching
```

### 10. Example Evaluation

**Full example:**
```
mas-lab/evaluations/design-patterns-comparison/
  evaluation.yaml
  datasets/
    math_reasoning.yaml
  experiments/
    cot.yaml
    react.yaml
    planner.yaml
  analysis/
    consolidate.yaml
  plots/
    latency_distribution.yaml
    success_rate.yaml
    pattern_comparison.yaml
    pareto_frontier.yaml
  output/
    .cache/
      dataset.fingerprint
      run_cot.fingerprint
      ...
    data/
      dataset/
        math_reasoning.json
      run_cot/
        001/run_001_.../ metadata.json, events.jsonl
      run_react/
        ...
      consolidate/
        consolidated.parquet
        statistics.csv
    plots/
      latency_distribution.svg
      pattern_comparison.svg
    logs/
      dataset.log
      run_cot.log
      ...
```

**evaluation.yaml:**
```yaml
pipeline:
  name: "design-patterns-comparison"
  version: "v1"
  description: "Compare CoT, ReAct, and Planner patterns on math reasoning"
  
  output:
    base_dir: "./output"
  
  steps:
    # Dataset
    - name: "dataset"
      type: "dataset"
      config: !include datasets/math_reasoning.yaml
    
    # Experiments (run in parallel)
    - name: "run_cot"
      type: "experiment"
      depends_on: ["dataset"]
      config: !include experiments/cot.yaml
    
    - name: "run_react"
      type: "experiment"
      depends_on: ["dataset"]
      config: !include experiments/react.yaml
    
    - name: "run_planner"
      type: "experiment"
      depends_on: ["dataset"]
      config: !include experiments/planner.yaml
    
    # Analysis
    - name: "consolidate"
      type: "analysis"
      depends_on: ["run_cot", "run_react", "run_planner"]
      config: !include analysis/consolidate.yaml
    
    # Plots (can run in parallel)
    - name: "plot_latency"
      type: "plot"
      depends_on: ["consolidate"]
      config: !include plots/latency_distribution.yaml
    
    - name: "plot_success"
      type: "plot"
      depends_on: ["consolidate"]
      config: !include plots/success_rate.yaml
    
    - name: "plot_comparison"
      type: "plot"
      depends_on: ["consolidate"]
      config: !include plots/pattern_comparison.yaml
    
    - name: "plot_pareto"
      type: "plot"
      depends_on: ["consolidate"]
      config: !include plots/pareto_frontier.yaml
```

**datasets/math_reasoning.yaml:**
```yaml
path: "labs/design-space.lab/01-design-patterns/datasets/qa-reasoning-queries-100.yaml"
filter:
  # category: "arithmetic"  # Optional
```

**experiments/cot.yaml:**
```yaml
manifest: "docs/tutorials/01-building-an-agent/agent.yaml"
n_runs: 5
timeout: 60
pause_between_runs: 1.0
```

**plots/latency_distribution.yaml:**
```yaml
type: "latency_distribution"
params:
  bins: 30
  title: "Latency Distribution by Pattern"
  x_label: "Latency (ms)"
  y_label: "Count"
  facet_by: "pattern"
```

### 11. Change Scenarios

**Scenario 1: Add new dataset item**
```bash
# Edit datasets/math_reasoning.yaml (add item "006")
mas-lab pipeline run evaluation.yaml

# Only runs:
# - dataset (recompute, detects new item)
# - run_cot, run_react, run_planner (only for item "006")
# - consolidate (re-merge with new data)
# - All plots (use updated dataframe)
```

**Scenario 2: Change experiment config**
```bash
# Edit experiments/cot.yaml (change n_runs: 3 → 5)
mas-lab pipeline run evaluation.yaml

# Only runs:
# - run_cot (add runs 4-5 to all items)
# - consolidate (re-merge)
# - All plots
```

**Scenario 3: Add new plot**
```bash
# Create plots/token_usage.yaml
# Add step to evaluation.yaml

mas-lab pipeline run evaluation.yaml

# Only runs:
# - plot_token_usage (new step)
```

**Scenario 4: Force full rerun**
```bash
mas-lab pipeline run evaluation.yaml --force dataset

# Runs everything (dataset change invalidates all downstream)
```

## Implementation Plan

### Phase 1: Core Pipeline System
1. `pipeline.py` - Pipeline, PipelineStep data structures
2. `resolver.py` - Dependency resolution (topological sort)
3. `cache.py` - Fingerprinting and cache management
4. `executor.py` - PipelineExecutor with rerun logic

### Phase 2: Step Implementations
1. `steps/dataset.py` - Dataset loading
2. `steps/experiment.py` - Experiment orchestration (reuse MultiRunOrchestrator)
3. `steps/analysis.py` - Result consolidation (reuse ResultAnalyzer)
4. `steps/plot.py` - Plot library specs (`config.spec`); use `plotnine` for ggplot pipelines

### Phase 3: CLI & Integration
1. Extend `mas-lab/src/mas/lab/cli.py` with pipeline commands
2. Create `mas-lab/evaluations/` directory structure
3. Migrate `exp-design-patterns/` to new pipeline format
4. Documentation and examples

### Phase 4: Advanced Features
1. Parallel execution (independent steps run concurrently)
2. Remote execution (run expensive experiments on remote workers)
3. Pipeline templates (reusable evaluation patterns)
4. Web UI for pipeline visualization and monitoring

## Benefits

1. **Declarative**: No Python code for common evaluations
2. **Reproducible**: Config + dataset → deterministic results
3. **Efficient**: Only rerun what changed
4. **Composable**: Mix and match steps, split/merge configs
5. **Transparent**: Clear dependency graph, execution plan
6. **Scalable**: Parallel execution, remote workers
7. **Maintainable**: Centralized pipeline definitions in mas-lab

## Migration Path

**Existing evaluations** (e.g., exp-design-patterns) can:
1. Keep current structure (no breaking changes)
2. Opt-in to pipeline system (create evaluation.yaml)
3. Gradually migrate plots/analysis to declarative format

**Timeline:**
- Week 1: Core pipeline system (Phase 1)
- Week 2: Step implementations (Phase 2)
- Week 3: CLI + migration example (Phase 3)
- Week 4+: Advanced features (Phase 4)
