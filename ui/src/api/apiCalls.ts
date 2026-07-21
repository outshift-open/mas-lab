//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useMutation, useQuery } from "@tanstack/react-query";

declare global {
  interface Window {
    __MAS_LAB_API_BASE_URL__?: string;
  }
}

/** Runtime override (Docker entrypoint) → Vite build-time env → local dev default. */
export const API_BASE_URL =
  (typeof window !== "undefined" && window.__MAS_LAB_API_BASE_URL__) ||
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  "http://localhost:8090";

// --- Libraries ---

export interface Library {
  dir: string;
  name: string;
  description: string;
}

async function fetchLibraries(): Promise<Library[]> {
  const response = await fetch(`${API_BASE_URL}/api/libraries`);
  if (!response.ok) {
    throw new Error(`Failed to fetch libraries: ${response.status}`);
  }
  const data = await response.json();
  return data.libraries;
}

export function useLibraries() {
  return useQuery({
    queryKey: ["libraries"],
    queryFn: fetchLibraries,
  });
}

export interface ValidateRequest {
  library: string;
  manifest_yaml: string;
}

interface ValidateResponse {
  exit_code: number;
  stdout: string;
  stderr: string;
  command: string;
}

async function validateManifest(
  request: ValidateRequest,
): Promise<ValidateResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${request.library}/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manifest_yaml: request.manifest_yaml }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Validation failed with status ${response.status}`,
    );
  }

  return response.json();
}

export function useValidateAgent() {
  return useMutation({
    mutationFn: validateManifest,
  });
}

export function useValidateMas() {
  return useMutation({
    mutationFn: validateManifest,
  });
}

// --- Tools ---

export interface ToolOption {
  name: string;
  description: string;
}

async function fetchTools(
  library: string,
  namespaces: string[] = ["global"],
): Promise<ToolOption[]> {
  const params = new URLSearchParams({
    namespaces: namespaces.join(","),
  });
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${library}/tools?${params}`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch tools: ${response.status}`);
  }
  const data = await response.json();
  return data.tools;
}

export function useTools(library: string, namespaces: string[] = ["global"]) {
  return useQuery({
    queryKey: ["tools", library, ...namespaces],
    queryFn: () => fetchTools(library, namespaces),
    enabled: !!library,
  });
}

// --- Skills ---

export interface SkillOption {
  name: string;
  description: string;
}

async function fetchSkills(
  library: string,
  namespaces: string[] = ["global"],
): Promise<SkillOption[]> {
  const ns = namespaces.join(",");
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${library}/skills?namespaces=${encodeURIComponent(ns)}`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch skills: ${response.status}`);
  }
  const data = await response.json();
  return data.skills;
}

export function useSkills(library: string, namespaces: string[] = ["global"]) {
  return useQuery({
    queryKey: ["skills", library, ...namespaces],
    queryFn: () => fetchSkills(library, namespaces),
    enabled: !!library,
  });
}

// --- Run Agent ---

export interface RunAgentRequest {
  library: string;
  manifest_yaml: string;
  query: string;
  flavour?: string;
  session_id?: string;
  verbose?: boolean;
  timeout?: number;
}

interface RunAgentSubmitResponse {
  job_id: string;
  status: string;
  command: string;
  session_id?: string;
}

export interface JobSubmitResponse {
  job_id: string;
  status: string;
  command: string;
}

export interface JobResponse {
  id: string;
  endpoint: string;
  command: string;
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "timeout";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  pid: number | null;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  error: string | null;
  response?: string;
  error_message?: string;
  error_detail?: string;
  session_id?: string;
}

export async function runAgent(
  request: RunAgentRequest,
): Promise<RunAgentSubmitResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${request.library}/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        manifest_yaml: request.manifest_yaml,
        query: request.query,
        ...(request.flavour && { flavour: request.flavour }),
        ...(request.session_id && { session_id: request.session_id }),
        verbose: request.verbose ?? false,
        timeout: request.timeout ?? 60,
      }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Run agent failed with status ${response.status}`,
    );
  }

  return response.json();
}

export interface JobSummary {
  id: string;
  endpoint: string;
  command: string;
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "timeout";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  pid: number | null;
  exit_code: number | null;
}

export interface JobDetail extends JobSummary {
  stdout: string;
  stderr: string;
  error: string | null;
  request_body?: Record<string, unknown>;
}

export async function fetchJobs(status?: string): Promise<JobSummary[]> {
  const url = new URL(`${API_BASE_URL}/api/jobs`);
  if (status) url.searchParams.set("status", status);
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`Failed to fetch jobs: ${response.status}`);
  }
  const data = await response.json();
  return data.jobs;
}

export async function fetchJobDetail(jobId: string): Promise<JobDetail> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`);
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `Failed to fetch job ${jobId}`);
  }
  return response.json();
}

export async function pollJob(jobId: string): Promise<JobResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`);

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? `Failed to poll job ${jobId}`);
  }

  return response.json();
}

// --- Run MAS ---

export interface RunMasRequest {
  library: string;
  manifest_yaml: string;
  query: string;
  overlays?: string[];
  flavour?: string;
  verbose?: boolean;
  timeout?: number;
}

export async function runMas(
  request: RunMasRequest,
): Promise<{ job_id: string; status: string; command: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${request.library}/run-mas`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        manifest_yaml: request.manifest_yaml,
        query: request.query,
        overlays: request.overlays ?? [],
        flavour: request.flavour,
        verbose: request.verbose ?? true,
        timeout: request.timeout ?? 600,
      }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Run MAS failed with status ${response.status}`,
    );
  }

  return response.json();
}

// --- Benchmark ---

export interface BenchmarkRunRequest {
  library: string;
  experiment_yaml: string;
  progress?: boolean;
  n_runs?: number;
  timeout?: number;
}

interface BenchmarkRunSubmitResponse {
  job_id: string;
  status: string;
  command: string;
}

// --- MAS Resources ---

export interface MasResourceEntry {
  mas_yaml: string;
  agents: Record<string, string>;
}

export interface MasResourceCreateRequest {
  library: string;
  mas_name: string;
  mas_yaml: string;
  agents: Record<string, string>;
}

export interface MasResourceUpdateRequest {
  library: string;
  old_mas_name: string;
  mas_name: string;
  mas_yaml: string;
  agents: Record<string, string>;
}

export interface MasResourceCreateResponse {
  mas_name: string;
  path: string;
  files: string[];
}

export interface MasResourceDetail {
  mas_name: string;
  mas_yaml: string;
  agents: Record<string, string>;
}

export async function fetchMasResources(
  library: string,
): Promise<Record<string, MasResourceEntry>> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${library}/apps`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch MAS resources: ${response.status}`);
  }
  const data = await response.json();
  return data.mas_resources;
}

export function useMasResources(library: string) {
  return useQuery({
    queryKey: ["apps", library],
    queryFn: () => fetchMasResources(library),
    enabled: !!library,
  });
}

export async function fetchMasResourceDetail(
  library: string,
  masName: string,
): Promise<MasResourceDetail> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${library}/apps/${masName}`,
  );
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`MAS resource "${masName}" not found`);
    }
    throw new Error(`Failed to fetch MAS resource: ${response.status}`);
  }
  return response.json();
}

export function useMasResourceDetail(library: string, masName: string) {
  return useQuery({
    queryKey: ["apps", library, masName],
    queryFn: () => fetchMasResourceDetail(library, masName),
    enabled: !!library && !!masName,
  });
}

export async function createMasResource(
  request: MasResourceCreateRequest,
): Promise<MasResourceCreateResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${request.library}/apps`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mas_name: request.mas_name,
        mas_yaml: request.mas_yaml,
        agents: request.agents,
      }),
    },
  );
  if (!response.ok) {
    if (response.status === 409) {
      throw new Error(
        `A MAS with the name "${request.mas_name}" already exists.`,
      );
    }
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to create MAS resource: ${response.status}`,
    );
  }
  return response.json();
}

export async function updateMasResource(
  request: MasResourceUpdateRequest,
): Promise<MasResourceCreateResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${request.library}/apps/${request.old_mas_name}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mas_name: request.mas_name,
        mas_yaml: request.mas_yaml,
        agents: request.agents,
      }),
    },
  );
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`MAS resource "${request.old_mas_name}" not found.`);
    }
    if (response.status === 409) {
      throw new Error(
        `A MAS with the name "${request.mas_name}" already exists.`,
      );
    }
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to update MAS resource: ${response.status}`,
    );
  }
  return response.json();
}

export async function deleteMasResource(
  library: string,
  masName: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${library}/apps/${masName}`,
    { method: "DELETE" },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error(`Failed to delete MAS resource: ${response.status}`);
  }
}

// --- Benchmark ---

export async function runBenchmark(
  request: BenchmarkRunRequest,
): Promise<BenchmarkRunSubmitResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${request.library}/benchmark/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        experiment_yaml: request.experiment_yaml,
        progress: request.progress ?? true,
        ...(request.n_runs != null && { max_runs: request.n_runs }),
        timeout: request.timeout ?? 1800,
      }),
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Benchmark run failed with status ${response.status}`,
    );
  }

  return response.json();
}

// --- Scenarios ---

export interface ScenarioEntry {
  name: string;
  path: string;
}

async function fetchScenarios(library: string): Promise<ScenarioEntry[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${library}/scenarios`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch scenarios: ${response.status}`);
  }
  const data = await response.json();
  return data.scenarios;
}

export function useScenarios(library: string) {
  return useQuery({
    queryKey: ["scenarios", library],
    queryFn: () => fetchScenarios(library),
    enabled: !!library,
  });
}

// --- Datasets ---

export interface DatasetEntry {
  name: string;
  path: string;
}

async function fetchDatasets(library: string): Promise<DatasetEntry[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${library}/datasets`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch datasets: ${response.status}`);
  }
  const data = await response.json();
  return data.datasets;
}

export function useDatasets(library: string) {
  return useQuery({
    queryKey: ["datasets", library],
    queryFn: () => fetchDatasets(library),
    enabled: !!library,
  });
}

// --- Experiments CRUD ---

export interface ExperimentSummary {
  name: string;
  description: string;
  version: string;
  scenarios: string[];
  dataset: string;
  library?: string;
  path?: string;
}

async function fetchAllExperiments(): Promise<ExperimentSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/definitions`);
  if (!response.ok) throw new Error("Failed to fetch experiments");
  const data = await response.json();
  return data.experiments ?? [];
}

async function fetchExperiments(library: string): Promise<ExperimentSummary[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/experiments`,
  );
  if (!response.ok) throw new Error("Failed to fetch experiments");
  const data = await response.json();
  return data.experiments ?? [];
}

/** All experiments across libraries (design-space, extensions, lifecycle-control, …). */
export function useAllExperiments() {
  return useQuery({
    queryKey: ["experiments", "all"],
    queryFn: fetchAllExperiments,
  });
}

export function useExperiments(library: string) {
  return useQuery({
    queryKey: ["experiments", library],
    queryFn: () => fetchExperiments(library),
    enabled: !!library,
  });
}

export interface ExperimentContentResponse {
  name: string;
  content: string;
}

export async function fetchExperimentContent(
  library: string,
  name: string,
): Promise<ExperimentContentResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/experiments/${encodeURIComponent(name)}`,
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to fetch experiment: ${response.status}`,
    );
  }
  return response.json();
}

export function useExperimentContent(library: string, name: string) {
  return useQuery({
    queryKey: ["experiment-content", library, name],
    queryFn: () => fetchExperimentContent(library, name),
    enabled: !!library && !!name,
  });
}

export async function createExperiment(
  library: string,
  payload: { name: string; content: string },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/experiments`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error
        ? JSON.stringify(error, null, 2)
        : `Failed to create experiment: ${response.status}`,
    );
  }
}

export async function updateExperimentApi(
  library: string,
  oldName: string,
  payload: { name: string; content: string },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/experiments/${encodeURIComponent(oldName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error
        ? JSON.stringify(error, null, 2)
        : `Failed to update experiment: ${response.status}`,
    );
  }
}

export async function deleteExperimentApi(
  library: string,
  name: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/experiments/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to delete experiment: ${response.status}`,
    );
  }
}

// --- Experiment Cache ---

export async function deleteExperimentCache(
  experimentName: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentName)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to delete experiment cache: ${response.status}`,
    );
  }
}

// --- Experiment Detail ---

export interface FileTreeEntry {
  name: string;
  type: "file" | "directory";
  children?: FileTreeEntry[];
}

export interface ExperimentDetail {
  name: string;
  metadata: Record<string, unknown>;
  tree: FileTreeEntry[];
}

async function fetchExperimentDetail(
  experimentName: string,
): Promise<ExperimentDetail> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentName)}`,
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to fetch experiment: ${response.status}`,
    );
  }
  return response.json();
}

export function useExperimentDetail(experimentName: string) {
  return useQuery({
    queryKey: ["experiment", experimentName],
    queryFn: () => fetchExperimentDetail(experimentName),
    enabled: !!experimentName,
  });
}

export interface ExperimentFileResponse {
  path: string;
  content: string;
}

export async function fetchExperimentFile(
  experimentName: string,
  filePath: string,
): Promise<ExperimentFileResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentName)}/file?path=${encodeURIComponent(filePath)}`,
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to fetch file: ${response.status}`,
    );
  }
  return response.json();
}

// --- Pipeline Step Types ---

export interface PipelineStepTypeConfigField {
  type: string;
  required?: boolean;
  default?: unknown;
  description?: string;
  enum?: string[];
}

export interface PipelineStepTypeEntry {
  type: string;
  label: string;
  description: string;
  phase: string;
  category: string;
  requires?: string;
  config: Record<string, PipelineStepTypeConfigField>;
}

export interface PipelineStepTypesResponse {
  step_types: PipelineStepTypeEntry[];
  categories: { id: string; label: string; color: string }[];
}

async function fetchPipelineStepTypes(): Promise<PipelineStepTypesResponse> {
  const response = await fetch(`${API_BASE_URL}/api/pipeline-step-types`);
  if (!response.ok) throw new Error("Failed to fetch pipeline step types");
  return response.json();
}

export function usePipelineStepTypes() {
  return useQuery({
    queryKey: ["pipeline-step-types"],
    queryFn: fetchPipelineStepTypes,
    staleTime: 5 * 60 * 1000,
  });
}

// --- Pipelines ---

export interface PipelineStepSummary {
  name: string;
  type: string;
  depends_on: string[];
}

export interface PipelineSummary {
  filename: string;
  name: string;
  description: string;
  steps: PipelineStepSummary[];
  experiment: string;
}

async function fetchPipelines(library: string): Promise<PipelineSummary[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/pipelines`,
  );
  if (!response.ok) throw new Error("Failed to fetch pipelines");
  const data = await response.json();
  return data.pipelines ?? [];
}

export function usePipelines(library: string) {
  return useQuery({
    queryKey: ["pipelines", library],
    queryFn: () => fetchPipelines(library),
    enabled: !!library,
  });
}

export interface PipelineDetail {
  name: string;
  content: string;
}

export async function fetchPipelineDetail(
  library: string,
  name: string,
): Promise<PipelineDetail> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/pipelines/${encodeURIComponent(name)}`,
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to fetch pipeline: ${response.status}`,
    );
  }
  return response.json();
}

export function usePipelineDetail(library: string, name: string) {
  return useQuery({
    queryKey: ["pipeline", library, name],
    queryFn: () => fetchPipelineDetail(library, name),
    enabled: !!library && !!name,
  });
}

export async function createPipeline(
  library: string,
  payload: { name: string; content: string },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/pipelines`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to create pipeline: ${response.status}`,
    );
  }
}

export async function updatePipeline(
  library: string,
  oldName: string,
  payload: { name: string; content: string },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/pipelines/${encodeURIComponent(oldName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to update pipeline: ${response.status}`,
    );
  }
}

export async function deletePipeline(
  library: string,
  name: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/pipelines/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to delete pipeline: ${response.status}`,
    );
  }
}

interface ValidateOverlayResponse {
  status: string;
  errors: string[];
}

export function useValidateOverlay() {
  return useMutation({
    mutationFn: async ({
      library,
      manifest_yaml,
    }: {
      library: string;
      manifest_yaml: string;
    }): Promise<ValidateOverlayResponse> => {
      const response = await fetch(
        `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/overlays/validate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ manifest_yaml }),
        },
      );
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        const detail = error?.detail;
        const errors = error?.errors;
        const msg = errors?.length
          ? errors.join("\n")
          : typeof detail === "string"
            ? detail
            : detail
              ? JSON.stringify(detail, null, 2)
              : "Validation failed";
        throw new Error(msg);
      }
      return response.json();
    },
  });
}

// --- Overlay CRUD ---

export interface OverlayEntry {
  name: string;
  description?: string;
  namespace?: string;
  path?: string;
}

export async function fetchOverlays(
  library: string,
): Promise<OverlayEntry[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/overlays`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch overlays: ${response.status}`);
  }
  const data = await response.json();
  return data.overlays as OverlayEntry[];
}

export function useOverlays(library: string) {
  return useQuery({
    queryKey: ["overlays", library],
    queryFn: () => fetchOverlays(library),
    enabled: !!library,
  });
}

export interface OverlayDetail {
  name: string;
  content: string;
}

export async function fetchOverlay(
  library: string,
  name: string,
): Promise<OverlayDetail> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/overlays/${encodeURIComponent(name)}`,
  );
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Overlay "${name}" not found`);
    }
    throw new Error(`Failed to fetch overlay: ${response.status}`);
  }
  return response.json();
}

export function useOverlay(library: string, name: string) {
  return useQuery({
    queryKey: ["overlay", library, name],
    queryFn: () => fetchOverlay(library, name),
    enabled: !!library && !!name,
  });
}

export async function createOverlay(
  library: string,
  payload: { name: string; content: string; run_validation?: boolean },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/overlays`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to create overlay: ${response.status}`,
    );
  }
}

export async function updateOverlay(
  library: string,
  overlayName: string,
  payload: { name: string; content: string; run_validation?: boolean },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/overlays/${encodeURIComponent(overlayName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to update overlay: ${response.status}`,
    );
  }
}

export async function deleteOverlayApi(
  library: string,
  name: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/overlays/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to delete overlay: ${response.status}`,
    );
  }
}

export function useValidatePipeline() {
  return useMutation({
    mutationFn: async ({
      library,
      content,
    }: {
      library: string;
      content: string;
    }) => {
      const response = await fetch(
        `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/pipelines/validate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ manifest_yaml: content }),
        },
      );
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        const detail = error?.detail;
        const msg =
          typeof detail === "string"
            ? detail
            : detail
              ? JSON.stringify(detail, null, 2)
              : "Validation failed";
        throw new Error(msg);
      }
      return response.json();
    },
  });
}

export async function runPipeline(
  library: string,
  payload: { pipeline_yaml: string; only?: string[]; timeout?: number },
): Promise<{ job_id: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/pipeline/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to run pipeline: ${response.status}`,
    );
  }
  return response.json();
}

// --- Metrics ---

export function useEvalMetrics() {
  return useQuery<Record<string, string>>({
    queryKey: ["metrics", "eval"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/metrics/eval`);
      if (!response.ok) throw new Error("Failed to fetch eval metrics");
      return response.json();
    },
  });
}

export function useMceMetrics() {
  return useQuery<Record<string, string>>({
    queryKey: ["metrics", "mce"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/metrics/mce`);
      if (!response.ok) throw new Error("Failed to fetch MCE metrics");
      return response.json();
    },
  });
}

// --- Datasets CRUD ---

export interface DatasetSummary {
  name: string;
  path: string;
  description: string;
}

export interface DatasetDetail {
  name: string;
  content: string;
}

export async function fetchDatasetsList(
  library: string,
): Promise<DatasetSummary[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/datasets`,
  );
  if (!response.ok)
    throw new Error(`Failed to fetch datasets: ${response.status}`);
  const data = await response.json();
  return data.datasets;
}

export function useDatasetsList(library: string) {
  return useQuery({
    queryKey: ["datasets-list", library],
    queryFn: () => fetchDatasetsList(library),
    enabled: !!library,
  });
}

export async function fetchDatasetDetail(
  library: string,
  name: string,
): Promise<DatasetDetail> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/datasets/${encodeURIComponent(name)}`,
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to fetch dataset: ${response.status}`,
    );
  }
  return response.json();
}

export function useDatasetDetail(library: string, name: string) {
  return useQuery({
    queryKey: ["dataset", library, name],
    queryFn: () => fetchDatasetDetail(library, name),
    enabled: !!library && !!name,
  });
}

export async function deleteDataset(
  library: string,
  name: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/datasets/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
  if (!response.ok && response.status !== 404) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Failed to delete dataset: ${response.status}`,
    );
  }
}

export interface UpdateDatasetPayload {
  name: string;
  content: string;
}

export async function updateDataset(
  library: string,
  currentName: string,
  payload: UpdateDatasetPayload,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/datasets/${encodeURIComponent(currentName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error
        ? JSON.stringify(error, null, 2)
        : `Failed to update dataset: ${response.status}`,
    );
  }
}

export function useUpdateDataset(library: string, currentName: string) {
  return useMutation({
    mutationFn: (payload: UpdateDatasetPayload) =>
      updateDataset(library, currentName, payload),
  });
}

export async function createDatasetApi(
  library: string,
  payload: UpdateDatasetPayload,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/datasets`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error
        ? JSON.stringify(error, null, 2)
        : `Failed to create dataset: ${response.status}`,
    );
  }
}

export function useCreateDataset(library: string) {
  return useMutation({
    mutationFn: (payload: UpdateDatasetPayload) =>
      createDatasetApi(library, payload),
  });
}

export function useDeleteDataset(library: string, name: string) {
  return useMutation({
    mutationFn: () => deleteDataset(library, name),
  });
}

// --- Config Files ---

export type ConfigFiles = Record<string, Record<string, string>>;

async function fetchConfigFiles(library: string): Promise<ConfigFiles> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/config-files`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch config files: ${response.status}`);
  }
  return response.json();
}

export function useConfigFiles(library: string) {
  return useQuery({
    queryKey: ["config-files", library],
    queryFn: () => fetchConfigFiles(library),
    enabled: !!library,
  });
}

// --- Runtime runners ---

export interface RuntimeRunner {
  id: string;
  label: string;
}

async function fetchRuntimeRunners(): Promise<RuntimeRunner[]> {
  const response = await fetch(`${API_BASE_URL}/api/runtime-runners`);
  if (!response.ok) {
    throw new Error(`Failed to fetch runtime runners: ${response.status}`);
  }
  const data = await response.json();
  return data.runners ?? [];
}

export function useRuntimeRunners() {
  return useQuery({
    queryKey: ["runtime-runners"],
    queryFn: fetchRuntimeRunners,
    staleTime: 5 * 60 * 1000,
  });
}

export async function analyzeBenchmark(
  library: string,
  payload: { benchmark_id: string; experiment_yaml?: string; timeout?: number },
): Promise<JobSubmitResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/benchmark/analyze`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Benchmark analyze failed with status ${response.status}`,
    );
  }
  return response.json();
}

export interface BenchmarkExportRequest {
  benchmark_id: string;
  output?: string;
  include_trace_cache?: boolean;
  dry_run?: boolean;
  timeout?: number;
}

export async function exportBenchmark(
  library: string,
  payload: BenchmarkExportRequest,
): Promise<JobSubmitResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/benchmark/export`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Benchmark export failed with status ${response.status}`,
    );
  }
  return response.json();
}

export async function downloadBenchmarkExport(
  library: string,
  benchmarkId: string,
): Promise<void> {
  const url = `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/benchmark/download?benchmark_id=${encodeURIComponent(benchmarkId)}`;
  const response = await fetch(url);
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Benchmark download failed with status ${response.status}`,
    );
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition");
  const filename =
    disposition?.match(/filename="?([^"]+)"?/)?.[1] ?? `${benchmarkId}.tar.gz`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export interface BenchmarkImportRequest {
  tarball: string;
  output_dir?: string;
  trace_cache_dir?: string;
  dry_run?: boolean;
  timeout?: number;
}

export async function importBenchmark(
  library: string,
  payload: BenchmarkImportRequest,
): Promise<JobSubmitResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/benchmark/import`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Benchmark import failed with status ${response.status}`,
    );
  }
  return response.json();
}

export async function uploadImportBenchmark(
  library: string,
  file: File,
): Promise<JobSubmitResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(
    `${API_BASE_URL}/api/libraries/${encodeURIComponent(library)}/benchmark/upload-import`,
    {
      method: "POST",
      body: formData,
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? `Benchmark upload-import failed with status ${response.status}`,
    );
  }
  return response.json();
}
