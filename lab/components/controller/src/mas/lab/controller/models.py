#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pydantic request/response models for the FastAPI controller API."""

from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, BaseModel, Field

from mas.lab.controller.constants import MAX_TIMEOUT


class ValidateRequest(BaseModel):
    manifest_yaml: str = Field(
        ...,
        description="Full YAML manifest content to validate (agent or MAS)",
    )


class SaveOverlayRequest(BaseModel):
    name: str = Field(..., description="Overlay name (used as filename, without .yaml)")
    content: str = Field(..., description="Full overlay YAML content")
    run_validation: bool = Field(default=True, description="Validate against schema before saving")


class RunAgentRequest(BaseModel):
    manifest_yaml: str = Field(..., description="Full agent YAML manifest content to run")
    query: str = Field(..., description="The question to send to the agent")
    flavour: Optional[str] = Field(
        default=None,
        description="Flavour name (e.g., 'local', 'mock', 'prod')",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Stable session id for multi-turn chat memory",
    )
    verbose: bool = Field(
        default=False,
        description="Deprecated: chat runs in-process without CLI stdout",
    )
    no_cache: bool = Field(default=True, description="Clear web search cache before running")
    timeout: int = Field(default=60, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class MultiTurnRequest(BaseModel):
    manifest_yaml: str = Field(..., description="Full agent YAML manifest content to run")
    queries: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of queries for a multi-turn conversation",
    )
    overlays: list[str] = Field(
        default_factory=list,
        description="Overlay filenames to apply (relative to library dir)",
    )
    flavour: Optional[str] = Field(default=None, description="Flavour name")
    verbose: bool = Field(default=True, description="Enable verbose output")
    timeout: int = Field(default=90, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class RunMASRequest(BaseModel):
    manifest_yaml: str = Field(..., description="Full MAS YAML manifest content to run")
    query: str = Field(..., description="The question to send to the MAS")
    overlays: list[str] = Field(
        default_factory=list,
        description="Overlay filenames to apply (relative to library dir)",
    )
    flavour: Optional[str] = Field(default=None, description="Flavour name")
    verbose: bool = Field(default=True, description="Enable verbose output")
    timeout: int = Field(default=90, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class SaveDatasetRequest(BaseModel):
    name: str = Field(..., description="Dataset filename (e.g. my-dataset.yaml)")
    content: str = Field(..., description="Full dataset YAML content")


class BenchmarkRunRequest(BaseModel):
    experiment_yaml: str = Field(
        ...,
        description="Full experiment YAML content, or a filename relative to the library dir",
    )
    progress: bool = Field(default=True, description="Show progress bar")
    max_runs: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("max_runs", "n_runs"),
        description="Override n_runs from config",
    )
    force: bool = Field(default=True, description="Force a new run even if a previous exists")
    flavour: Optional[str] = Field(default=None, description="Flavour name")
    timeout: int = Field(default=MAX_TIMEOUT, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class BenchmarkAnalyzeRequest(BaseModel):
    benchmark_id: str = Field(..., description="Benchmark run id (short or full)")
    experiment_yaml: Optional[str] = Field(
        default=None,
        description="Optional experiment YAML path when auto-detect fails",
    )
    timeout: int = Field(default=120, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class BenchmarkExportRequest(BaseModel):
    benchmark_id: str = Field(..., description="Benchmark run id (short, full, last, or latest)")
    output: Optional[str] = Field(default=None, description="Output .tar.gz path (default: cwd)")
    include_trace_cache: bool = Field(default=True, description="Pack trace-cache entries")
    dry_run: bool = Field(default=False, description="List archive contents without writing")
    timeout: int = Field(default=300, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class BenchmarkImportRequest(BaseModel):
    tarball: str = Field(..., description="Path to .tar.gz produced by benchmark export")
    output_dir: Optional[str] = Field(default=None, description="Restore benchmark output here")
    trace_cache_dir: Optional[str] = Field(default=None, description="Restore trace-cache entries here")
    dry_run: bool = Field(default=False, description="Inspect archive without writing")
    timeout: int = Field(default=300, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class PipelineRunRequest(BaseModel):
    pipeline_yaml: str = Field(
        default="pipelines/full-pipeline-topology-comparison.yaml",
        description="Pipeline YAML path (relative to library dir)",
    )
    only: list[str] = Field(
        default_factory=list,
        description="Run only these steps (e.g., ['extract', 'evaluate'])",
    )
    timeout: int = Field(default=MAX_TIMEOUT, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class SavePipelineRequest(BaseModel):
    name: str = Field(..., description="Pipeline name (used as filename, without .yaml)")
    content: str = Field(..., description="Full pipeline YAML content")
    run_validation: bool = Field(default=True, description="Validate against schema before saving")


class SaveExperimentRequest(BaseModel):
    name: str = Field(..., description="Experiment name (used as filename, without .yaml)")
    content: str = Field(..., description="Full experiment YAML content")


class EvalOutputRequest(BaseModel):
    events_file: str = Field(
        ...,
        description="Path to events.jsonl (relative to library dir or absolute)",
    )
    metrics: list[str] = Field(
        default=["AnswerRelevancyMetric"],
        description="Metric names to compute",
    )
    model: str = Field(default="azure/gpt-4o", description="LLM judge model")
    timeout: int = Field(default=90, ge=1, le=MAX_TIMEOUT, description="Timeout in seconds")


class SaveMASResourceRequest(BaseModel):
    mas_name: str = Field(..., description="MAS name (becomes the app folder name under apps/)")
    mas_yaml: str = Field(..., description="MAS manifest YAML content")
    agents: dict[str, str] = Field(
        default_factory=dict,
        description="Map of agent name → agent YAML content (stored in apps/<mas_name>/agents/)",
    )
