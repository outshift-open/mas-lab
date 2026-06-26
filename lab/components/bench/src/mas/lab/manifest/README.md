<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Manifest loading in mas-lab bench

Two packages — different manifest kinds:

| Import | Loads |
|--------|--------|
| `mas.lab.manifest` | **MAS / agent** YAML via ctl compose (`load_mas_config`, `load_agent_for_bench`) |
| `mas.lab.manifests` | **Experiment / pipeline** YAML with version shims (`load_experiment_data`, `load_pipeline_data`) |

Do not merge these trees; experiment versioning shims must stay isolated from ctl compose.
