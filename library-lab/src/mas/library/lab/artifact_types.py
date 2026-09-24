#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Artifact kinds declared by mas-library-lab.

Each class is a library.yaml ``type: artifact`` plugin
(``type`` / ``name`` / ``module`` / ``class``).
"""

from __future__ import annotations

from mas.lab.lab.config.artifact_types import ArtifactType


class Trace(ArtifactType):
    path = "{run_dir}/traces/events.jsonl"
    format = "jsonl"
    description = "Raw observability event stream from a single run."


class RunInfo(ArtifactType):
    path = "{run_dir}/run_info.json"
    format = "json"
    description = "Run metadata (hash, model, timing, status)."


class Plot(ArtifactType):
    path = "{level_dir}/plot.png"
    format = "png"
    description = "Visualization output (PNG, SVG, HTML, or PDF)."


class Metrics(ArtifactType):
    path = "{level_dir}/metrics.json"
    format = "json"
    schema = "artefacts/metrics.schema.json"
    description = "Quality metrics computed by evaluation providers."


class DataFrame(ArtifactType):
    path = "{level_dir}/data.csv"
    format = "csv"
    description = "Tidy CSV dataframe for analysis and plotting."
