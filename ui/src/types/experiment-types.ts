//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
export type OverlayRef = string | { ref: string };

export interface ExperimentScenario {
  id: string;
  description?: string;
  version?: number;
  overlays?: OverlayRef[];
  tags?: string[];
  user_prompt?: string;
  pipeline_resources?: Record<string, unknown>[];
}

export interface ExperimentDataset {
  path: string;
}

export interface ExperimentEvaluationConfig {
  metrics?: string[];
  criteria?: string[];
  metric_kwargs?: {
    model?: string;
    threshold?: number;
    api_key_env?: string;
  };
}

export interface ExperimentEvaluation {
  method: string;
  config: ExperimentEvaluationConfig;
}

export interface ExperimentMas {
  manifest?: string;
  configs_dir?: string;
}

export type InfraLlmMode = "live" | "mock" | "replay";
export type InfraToolsMode = "live" | "mock" | "stub";
export type InfraMemoryMode = "live" | "mock" | "snapshot" | "seeded" | "ephemeral";
export type InfraEmbeddingsMode = "live" | "mock" | "replay";
export type InfraStateMode = "live" | "snapshot" | "seeded" | "ephemeral" | "mock";

export interface InfraEmulation {
  llm?: InfraLlmMode;
  tools?: InfraToolsMode;
  memory?: InfraMemoryMode;
  embeddings?: InfraEmbeddingsMode;
  state?: InfraStateMode;
}

export type RuntimeTransportMode = "local" | "grpc" | "emulated";
export type RuntimeCacheMode = "content-addressed" | "disabled" | "forced";

export interface RuntimeEmulation {
  transport?: RuntimeTransportMode;
  cache?: RuntimeCacheMode;
}

export interface InterceptEmulation {
  mitm?: boolean;
  hooks?: string[];
}

export interface ExperimentEmulation {
  infra?: InfraEmulation;
  runtime?: RuntimeEmulation;
  intercept?: InterceptEmulation;
}

export interface ReplaySpec {
  mode?: "scripted" | "cache-and-diverge";
  hitl_source?: "dataset" | "recording";
  recording_path?: string;
  diverge_from_cache?: boolean;
}

export interface ExperimentExecution {
  n_runs: number;
  parallel_scenarios?: number;
  timeout?: number;
  pause_between_runs?: number;
  strategy?: string;
  replay?: ReplaySpec;
  emulation?: ExperimentEmulation;
}

export interface FlavourSpec {
  mode?: string;
  instrumentation?: string;
}

export interface PlotSpec {
  type: string;
  params?: Record<string, unknown>;
}

export interface PipelineStepSpec {
  type: string;
  name?: string;
  per_scenario?: boolean;
  phase?: "pre" | "post";
  scope?: string;
  config?: Record<string, unknown>;
  depends_on?: string[];
  in?: string | string[];
  out?: string | string[];
}

export interface ArtifactSpec {
  type: string;
  path?: string;
  validate?: boolean;
}

export interface LevelSpec {
  artifacts?: Record<string, string | ArtifactSpec>;
  pipeline?: PipelineStepSpec[];
}

export interface Experiment {
  name: string;
  version?: string;
  description?: string;
  mas: ExperimentMas;
  scenarios: ExperimentScenario[];
  dataset?: ExperimentDataset;
  evaluation?: ExperimentEvaluation;
  execution: ExperimentExecution;
  output_dir?: string;
  trace_cache_dir?: string;
  flavours?: Record<string, FlavourSpec>;
  default_flavour?: string;
  plots?: Record<string, PlotSpec>;
  pipeline?: PipelineStepSpec[];
  pipeline_resources?: Record<string, unknown>[];
  artifacts?: Record<string, string | ArtifactSpec>;
  run?: LevelSpec;
  test?: LevelSpec;
  scenario?: LevelSpec;
}
