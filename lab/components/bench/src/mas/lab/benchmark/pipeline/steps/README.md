# Pipeline step library (OSS)

One **step type** = one **Python module** under a category folder.

| Category | Path | Step types |
|----------|------|------------|
| **extract** | `extract/` | `extract_trace_stats`, `extract_mealy_stats`, `extract_sys_stats`, `extract_trajectories` |
| **eval** | `eval/` | `eval_mce`, `eval_batch`, `eval_adversarial`, `eval_trip_planner_gt`, `annotate_metrics`, `collect_metrics`, `compute_ci`, `compute_drift`, `validate_outputs` |
| **viz** | `viz/` | `plot`, `plot_trajectory`, `plot_trajectory_batch`, `plot_multilevel_trajectory`, `plot_multilevel_trajectory_batch`, `plot_communication_flow`, `plot_message_graph`, `ggplot`, `plotnine`, `ci_plot`, `metrics_comparison_plot`, `pipeline_diagram` |
| **data** | `data/` | `dataset`, `experiment`, `analysis`, `to_dataframe`, `to_impact_dataframe`, `join_dataframe`, `collect_dataframe`, `gather_level`, `diff_trajectories`, `embed_trajectories`, `generate_dataset`, `serialize`, `deserialize`, `processor` |
| **services** | `services/` | `service_start`, `service_stop`, `export_otel` |

Shared utilities (not registered step types): `pipeline/lib/data_source.py`, `pipeline/lib/plot_lib.py`, `pipeline/lib/plot_specs/`.

## Internal extensions

Steps that depend on corporate infra or KG pipelines live in **`mas-lab-internal/lab-components/bench-steps`** and register through the `mas.lab.pipeline_steps` entry-point group when that package is installed (dual-venv). Examples: `embed_states`, `list_clickhouse_sessions`.

## Adding a step

1. Add `steps/<category>/<name>.py` with a single `PipelineStep` subclass; set `type = "<step_id>"`.
2. Export the class from `steps/__init__.py` and map `type` → class in `pipeline/registry.py`.
3. Document the step in `lab/docs/pipeline-steps.md`.

Lab-local steps can instead use `register_step_type()` from `lib/steps/` (see paper labs).
