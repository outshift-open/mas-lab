//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { Add as AddIcon, Delete as DeleteIcon } from "@mui/icons-material";
import { stringify } from "yaml";
import type {
  Experiment,
  ExperimentScenario,
  InfraLlmMode,
  InfraToolsMode,
  OverlayRef,
  RuntimeCacheMode,
} from "@/types/experiment-types";
import type { OverlayEntry } from "@/api/apiCalls";
import { CodeBlock } from "@/components";
import { TabPanel } from "@/components/TabPanel/TabPanel";
import { useScenarios, useDatasets, useOverlays } from "@/api/apiCalls";

interface ExperimentModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (experiment: Experiment) => void | Promise<void>;
  editingExperiment?: Experiment | null;
  library: string;
}

interface ScenarioFormData {
  id: string;
  description: string;
  tags: string;
  overlays: string[];
}

/**
 * Convert an overlay display name (used in the UI multi-select) back to a
 * ``{ref: path}`` object for the experiment YAML.
 *
 * Display names use the ``global/`` prefix for library-root overlays;
 * app-scoped overlays use their bare name.  The ``path`` field from the
 * OverlayEntry carries the filesystem-relative path.
 */
function overlayDisplayNameToRef(
  displayName: string,
  overlayOptions: OverlayEntry[],
): { ref: string } | string {
  const match = overlayOptions.find((o) => overlayDisplayName(o) === displayName);
  if (match?.path) return { ref: match.path };
  return displayName;
}

/** Build a UI display name for an overlay entry: ``global/name`` or bare ``name``. */
function overlayDisplayName(entry: OverlayEntry): string {
  if (!entry.namespace || entry.namespace === "global") {
    return `global/${entry.name}`;
  }
  return entry.name;
}

/**
 * Convert an ``OverlayRef`` from an experiment YAML (either a bare string or
 * ``{ref: path}``) back to a UI display name for the multi-select.
 */
function overlayRefToDisplayName(
  ref: OverlayRef,
  overlayOptions: OverlayEntry[],
): string {
  if (typeof ref === "string") return ref;
  const path = ref.ref;
  const match = overlayOptions.find((o) => o.path === path);
  if (match) return overlayDisplayName(match);
  const stem = path.replace(/\.yaml$/, "").split("/").pop() ?? path;
  return stem;
}

function OverlaySelect({
  value,
  onChange,
  overlays,
}: {
  value: string[];
  onChange: (val: string[]) => void;
  overlays: OverlayEntry[];
}) {
  const sorted = useMemo(
    () => [
      ...overlays.filter((o) => !o.namespace || o.namespace === "global"),
      ...overlays.filter((o) => o.namespace && o.namespace !== "global"),
    ],
    [overlays],
  );

  const selected = value[0] ?? "";

  return (
    <FormControl variant="standard" sx={{ minWidth: 250, flex: 1 }}>
      <InputLabel>Overlay</InputLabel>
      <Select
        value={selected}
        label="Overlay"
        onChange={(e) => {
          const v = e.target.value as string;
          onChange(v ? [v] : []);
        }}
      >
        <MenuItem value="">
          <em>None</em>
        </MenuItem>
        {sorted.map((o) => {
          const dn = overlayDisplayName(o);
          return (
            <MenuItem key={dn} value={dn}>
              {dn}
            </MenuItem>
          );
        })}
      </Select>
    </FormControl>
  );
}

export const AddExperimentModal = ({
  open,
  onClose,
  onSave,
  editingExperiment,
  library,
}: ExperimentModalProps) => {
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [configsDir, setConfigsDir] = useState("apps");
  const [masManifest, setMasManifest] = useState("");
  const [usePatchOverlays, setUsePatchOverlays] = useState(false);

  const [scenarios, setScenarios] = useState<ScenarioFormData[]>([
    { id: "", description: "", tags: "", overlays: [] },
  ]);

  const [datasetPath, setDatasetPath] = useState("");

  const [nRuns, setNRuns] = useState("1");
  const [parallelScenarios, setParallelScenarios] = useState("3");
  const [timeout, setTimeout] = useState("300");
  const [pauseBetweenRuns, setPauseBetweenRuns] = useState("1.0");
  const [strategy, setStrategy] = useState("coverage");

  const [infraLlm, setInfraLlm] = useState<InfraLlmMode>("live");
  const [infraTools, setInfraTools] = useState<InfraToolsMode>("live");
  const [runtimeCache, setRuntimeCache] =
    useState<RuntimeCacheMode>("content-addressed");

  const [error, setError] = useState("");
  const [selectedTab, setSelectedTab] = useState(0);

  const { data: scenarioOptions = [] } = useScenarios(library);
  const { data: datasetOptions = [] } = useDatasets(library);
  const { data: overlayOptions = [] } = useOverlays(library);

  const filteredOverlays = useMemo(() => {
    if (!usePatchOverlays) return overlayOptions;
    const globalOnly = overlayOptions.filter(
      (o) => !o.namespace || o.namespace === "global",
    );
    if (!masManifest.trim()) return globalOnly;
    return overlayOptions.filter(
      (o) =>
        !o.namespace ||
        o.namespace === "global" ||
        o.namespace === masManifest.trim(),
    );
  }, [overlayOptions, usePatchOverlays, masManifest]);

  const isEditing = Boolean(editingExperiment);

  useEffect(() => {
    if (open && editingExperiment) {
      populateFromExperiment(editingExperiment);
    } else if (open && !editingExperiment) {
      resetForm();
    }
  }, [open, editingExperiment]);

  const populateFromExperiment = (exp: Experiment) => {
    setName(exp.name);
    setDescription(exp.description ?? "");
    const app0 = exp.applications?.[0];
    setConfigsDir(app0?.configs_dir ?? "apps");
    const rawManifest = app0?.manifest ?? "";
    setMasManifest(
      rawManifest.replace(/^apps\//, "").replace(/\/mas\.yaml$/, "").replace(/\.yaml$/, ""),
    );

    const hasOverlays =
      exp.scenarios?.some((s) => {
        const ov = s.overlays;
        if (!ov) return false;
        return (ov.logic?.length ?? 0) + (ov.control?.length ?? 0) + (ov.infra?.length ?? 0) > 0;
      }) ?? false;
    setUsePatchOverlays(hasOverlays);

    setScenarios(
      exp.scenarios?.length
        ? exp.scenarios.map((s) => {
            const allOverlays = [
              ...(s.overlays?.logic ?? []),
              ...(s.overlays?.control ?? []),
              ...(s.overlays?.infra ?? []),
            ];
            return {
              id: s.id,
              description: s.description ?? "",
              tags: s.tags?.join(", ") ?? "",
              overlays: allOverlays.map((ov) =>
                overlayRefToDisplayName(ov, overlayOptions),
              ),
            };
          })
        : [{ id: "", description: "", tags: "", overlays: [] }],
    );
    setDatasetPath(exp.dataset?.path ?? "");
    setNRuns(exp.run?.n_runs?.toString() ?? "1");
    setParallelScenarios(exp.execution?.parallel_scenarios?.toString() ?? "3");
    setTimeout(exp.execution?.timeout?.toString() ?? "300");
    setPauseBetweenRuns(exp.execution?.pause_between_runs?.toString() ?? "1.0");
    setStrategy(exp.execution?.strategy ?? "coverage");
    setInfraLlm(exp.execution?.emulation?.infra?.llm ?? "live");
    setInfraTools(exp.execution?.emulation?.infra?.tools ?? "live");
    setRuntimeCache(
      exp.execution?.emulation?.runtime?.cache ?? "content-addressed",
    );
    setError("");
    setSelectedTab(0);
  };

  const buildExperimentObject = (): Record<string, unknown> => {
    const builtScenarios = scenarios
      .filter((s) => s.id.trim())
      .map((s) => {
        const entry: Record<string, unknown> = { id: s.id.trim() };
        if (s.description.trim()) entry.description = s.description.trim();
        const tags = s.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
        if (tags.length) entry.tags = tags;
        if (usePatchOverlays && s.overlays.length > 0) {
          entry.overlays = {
            logic: s.overlays.map((displayName) =>
              overlayDisplayNameToRef(displayName, overlayOptions),
            ),
            control: [],
            infra: [],
          };
        }
        return entry;
      });

    const experiment: Record<string, unknown> = {};
    if (name.trim()) experiment.name = name.trim();
    if (description.trim()) experiment.description = description.trim();

    const appEntry: Record<string, unknown> = {};
    if (usePatchOverlays && masManifest.trim())
      appEntry.manifest = `apps/${masManifest.trim()}/mas.yaml`;
    if (!usePatchOverlays && configsDir.trim())
      appEntry.configs_dir = configsDir.trim();
    if (Object.keys(appEntry).length) experiment.applications = [appEntry];

    if (builtScenarios.length) experiment.scenarios = builtScenarios;

    if (datasetPath.trim()) experiment.dataset = { path: datasetPath.trim() };

    experiment.run = { n_runs: parseInt(nRuns, 10) || 1 };

    experiment.execution = {
      parallel_scenarios: parseInt(parallelScenarios, 10) || undefined,
      timeout: parseInt(timeout, 10) || undefined,
      pause_between_runs: parseFloat(pauseBetweenRuns) || undefined,
      strategy: strategy.trim() || undefined,
      emulation: {
        infra: { llm: infraLlm, tools: infraTools },
        runtime: { cache: runtimeCache },
      },
    };

    return { experiment };
  };

  const yamlPreview = useMemo(
    () => stringify(buildExperimentObject(), { lineWidth: 120 }),
    [
      name,
      description,
      configsDir,
      masManifest,
      scenarios,
      usePatchOverlays,
      datasetPath,
      nRuns,
      parallelScenarios,
      timeout,
      pauseBetweenRuns,
      strategy,
      infraLlm,
      infraTools,
      runtimeCache,
    ],
  );

  const addScenario = () => {
    setScenarios([
      ...scenarios,
      { id: "", description: "", tags: "", overlays: [] },
    ]);
  };

  const removeScenario = (index: number) => {
    setScenarios(scenarios.filter((_, i) => i !== index));
  };

  const updateScenario = (
    index: number,
    field: keyof ScenarioFormData,
    value: string | string[],
  ) => {
    const updated = [...scenarios];
    updated[index] = { ...updated[index], [field]: value };
    setScenarios(updated);
  };

  const handlePatchOverlaysToggle = (checked: boolean) => {
    setUsePatchOverlays(checked);
    setConfigsDir(checked ? "overlays" : "apps");
    setScenarios([{ id: "", description: "", tags: "", overlays: [] }]);
  };

  const handleSave = async () => {
    setError("");

    const trimmedName = name.trim();
    if (!trimmedName) return;

    const builtScenarios: ExperimentScenario[] = scenarios
      .filter((s) => s.id.trim())
      .map((s) => ({
        id: s.id.trim(),
        description: s.description.trim() || undefined,
        tags: s.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        overlays:
          usePatchOverlays && s.overlays.length > 0
            ? {
                logic: s.overlays.map((dn) =>
                  overlayDisplayNameToRef(dn, overlayOptions),
                ),
                control: [],
                infra: [],
              }
            : undefined,
      }));

    const experiment: Experiment = {
      name: trimmedName,
      description: description.trim() || undefined,
      applications: [
        {
          ...(usePatchOverlays && masManifest.trim()
            ? { manifest: `apps/${masManifest.trim()}/mas.yaml` }
            : {}),
          ...(!usePatchOverlays && configsDir.trim()
            ? { configs_dir: configsDir.trim() }
            : {}),
        },
      ],
      scenarios: builtScenarios,
      dataset: datasetPath.trim() ? { path: datasetPath.trim() } : undefined,
      run: { n_runs: parseInt(nRuns, 10) || 1 },
      execution: {
        parallel_scenarios: parseInt(parallelScenarios, 10) || undefined,
        timeout: parseInt(timeout, 10) || undefined,
        pause_between_runs: parseFloat(pauseBetweenRuns) || undefined,
        strategy: strategy.trim() || undefined,
        emulation: {
          infra: {
            llm: infraLlm,
            tools: infraTools,
          },
          runtime: {
            cache: runtimeCache,
          },
        },
      },
    };

    setSaving(true);
    try {
      await onSave(experiment);
      resetForm();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setName("");
    setDescription("");
    setConfigsDir("apps");
    setMasManifest("");
    setUsePatchOverlays(false);
    setScenarios([{ id: "", description: "", tags: "", overlays: [] }]);
    setDatasetPath("");
    setNRuns("1");
    setParallelScenarios("3");
    setTimeout("300");
    setPauseBetweenRuns("1.0");
    setStrategy("coverage");
    setInfraLlm("live");
    setInfraTools("live");
    setRuntimeCache("content-addressed");
    setError("");
    setSelectedTab(0);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        {isEditing ? "Edit Experiment" : "Add Experiment"}
      </DialogTitle>
      <DialogContent
        sx={{
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          padding: 0,
        }}
      >
        <Box sx={{ paddingLeft: "24px" }}>
          <Tabs value={selectedTab} onChange={(_, v) => setSelectedTab(v)}>
            <Tab label="Form" />
            <Tab label="YAML" />
          </Tabs>
        </Box>

        <TabPanel
          value={selectedTab}
          index={0}
          sx={{ flex: 1, overflow: "auto" }}
        >
          <Stack sx={{ gap: "16px", mt: "8px", padding: "8px 24px" }}>
            {error && <Alert severity="error">{error}</Alert>}

            <Typography variant="subtitle2" color="text.secondary">
              Basic Info
            </Typography>
            <Stack direction="row" sx={{ gap: "16px" }}>
              <TextField
                label="Name"
                placeholder="Enter experiment name"
                variant="standard"
                autoComplete="off"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                fullWidth
                error={Boolean(error)}
              />
            </Stack>
            <TextField
              label="Description"
              placeholder="Enter a description for this experiment"
              variant="standard"
              autoComplete="off"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              multiline
              rows={2}
              fullWidth
            />

            <Divider />

            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
            >
              <Stack
                direction="column"
                alignItems="flex-start"
                sx={{ gap: "4px" }}
              >
                <Typography variant="subtitle2" color="text.secondary">
                  Scenarios
                </Typography>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={usePatchOverlays}
                      onChange={(e) =>
                        handlePatchOverlaysToggle(e.target.checked)
                      }
                      size="small"
                    />
                  }
                  label={
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ marginLeft: "4px" }}
                    >
                      Use Patch Overlays
                    </Typography>
                  }
                  sx={{ marginLeft: 0 }}
                />
              </Stack>
              <IconButton size="small" onClick={addScenario}>
                <AddIcon fontSize="small" />
              </IconButton>
            </Stack>
            {scenarios.map((scenario, index) => (
              <Stack
                key={index}
                direction="row"
                sx={{ gap: "8px" }}
                alignItems="center"
                justifyContent="center"
              >
                {usePatchOverlays ? (
                  <TextField
                    label="ID"
                    placeholder="scenario-id"
                    variant="standard"
                    autoComplete="off"
                    value={scenario.id}
                    onChange={(e) =>
                      updateScenario(index, "id", e.target.value)
                    }
                    required
                    sx={{ width: 280 }}
                  />
                ) : (
                  <FormControl variant="standard" required sx={{ width: 350 }}>
                    <InputLabel>ID</InputLabel>
                    <Select
                      value={scenario.id}
                      label="ID"
                      onChange={(e) =>
                        updateScenario(index, "id", e.target.value)
                      }
                    >
                      {scenarioOptions
                        .filter(
                          (s) =>
                            s.name === scenario.id ||
                            !scenarios.some((sc) => sc.id === s.name),
                        )
                        .map((s) => (
                          <MenuItem key={s.name} value={s.name}>
                            {s.name}
                          </MenuItem>
                        ))}
                    </Select>
                  </FormControl>
                )}

                {usePatchOverlays && (
                  <OverlaySelect
                    value={scenario.overlays}
                    onChange={(val) => updateScenario(index, "overlays", val)}
                    overlays={filteredOverlays}
                  />
                )}

                <TextField
                  label="Description"
                  placeholder="Scenario description"
                  variant="standard"
                  autoComplete="off"
                  value={scenario.description}
                  onChange={(e) =>
                    updateScenario(index, "description", e.target.value)
                  }
                  fullWidth
                />
                <TextField
                  label="Tags"
                  placeholder="tag1, tag2"
                  variant="standard"
                  autoComplete="off"
                  value={scenario.tags}
                  onChange={(e) =>
                    updateScenario(index, "tags", e.target.value)
                  }
                  sx={{ width: 250 }}
                />
                {scenarios.length > 1 && (
                  <IconButton
                    size="medium"
                    onClick={() => removeScenario(index)}
                    sx={{ marginTop: "20px !important" }}
                  >
                    <DeleteIcon fontSize="medium" />
                  </IconButton>
                )}
              </Stack>
            ))}

            {usePatchOverlays && (
              <>
                <Divider />

                <Typography variant="subtitle2" color="text.secondary">
                  MAS Configuration
                </Typography>
                <FormControl variant="standard" required fullWidth>
                  <InputLabel>Base MAS Application</InputLabel>
                  <Select
                    value={masManifest}
                    label="Base MAS Application"
                    onChange={(e) => {
                      setMasManifest(e.target.value);
                      setScenarios((prev) =>
                        prev.map((s) => ({ ...s, overlays: [] })),
                      );
                    }}
                  >
                    {scenarioOptions.map((s) => (
                      <MenuItem key={s.name} value={s.name}>
                        {s.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </>
            )}

            <Divider />

            <Typography variant="subtitle2" color="text.secondary">
              Dataset
            </Typography>
            <FormControl variant="standard" required fullWidth>
              <InputLabel>Dataset Path</InputLabel>
              <Select
                value={datasetPath}
                label="Dataset Path"
                onChange={(e) => setDatasetPath(e.target.value)}
              >
                {datasetOptions
                  .filter((d) => d.name.endsWith(".yaml") || d.name.endsWith(".yml"))
                  .map((d) => (
                    <MenuItem key={d.path} value={d.path}>
                      {d.path.replace(/^datasets\//, "")}
                    </MenuItem>
                  ))}
              </Select>
            </FormControl>

            <Divider />

            <Typography variant="subtitle2" color="text.secondary">
              Execution
            </Typography>
            <Stack direction="row" sx={{ gap: "16px" }}>
              <TextField
                label="Number of Runs"
                placeholder="1"
                variant="standard"
                autoComplete="off"
                value={nRuns}
                onChange={(e) => setNRuns(e.target.value)}
                type="number"
                required
                slotProps={{ htmlInput: { min: 1 } }}
                sx={{ width: 140 }}
              />
              <TextField
                label="Parallel Scenarios"
                placeholder="3"
                variant="standard"
                autoComplete="off"
                value={parallelScenarios}
                onChange={(e) => setParallelScenarios(e.target.value)}
                type="number"
                required
                slotProps={{ htmlInput: { min: 1 } }}
                sx={{ width: 160 }}
              />
              <TextField
                label="Timeout (s)"
                placeholder="300"
                variant="standard"
                autoComplete="off"
                value={timeout}
                onChange={(e) => setTimeout(e.target.value)}
                type="number"
                required
                slotProps={{ htmlInput: { min: 1 } }}
                sx={{ width: 130 }}
              />
              <TextField
                label="Pause Between Runs (s)"
                placeholder="1.0"
                variant="standard"
                autoComplete="off"
                value={pauseBetweenRuns}
                onChange={(e) => setPauseBetweenRuns(e.target.value)}
                type="number"
                required
                slotProps={{ htmlInput: { step: 0.5, min: 0 } }}
                sx={{ width: 180 }}
              />
              <FormControl variant="standard" required sx={{ width: 160 }}>
                <InputLabel>Strategy</InputLabel>
                <Select
                  value={strategy}
                  label="Strategy"
                  onChange={(e) => setStrategy(e.target.value)}
                >
                  <MenuItem value="coverage">coverage</MenuItem>
                  <MenuItem value="random">random</MenuItem>
                  <MenuItem value="sequential">sequential</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            <Divider />

            <Typography variant="subtitle2" color="text.secondary">
              Emulation
            </Typography>
            <Stack direction="row" sx={{ gap: "16px" }}>
              <FormControl variant="standard" required sx={{ width: 150 }}>
                <InputLabel>Infra LLM</InputLabel>
                <Select
                  value={infraLlm}
                  label="Infra LLM"
                  onChange={(e) => setInfraLlm(e.target.value as InfraLlmMode)}
                >
                  <MenuItem value="live">live</MenuItem>
                  <MenuItem value="mock">mock</MenuItem>
                  <MenuItem value="replay">replay</MenuItem>
                </Select>
              </FormControl>
              <FormControl variant="standard" required sx={{ width: 150 }}>
                <InputLabel>Infra Tools</InputLabel>
                <Select
                  value={infraTools}
                  label="Infra Tools"
                  onChange={(e) =>
                    setInfraTools(e.target.value as InfraToolsMode)
                  }
                >
                  <MenuItem value="live">live</MenuItem>
                  <MenuItem value="mock">mock</MenuItem>
                  <MenuItem value="stub">stub</MenuItem>
                </Select>
              </FormControl>
              <FormControl variant="standard" required sx={{ width: 200 }}>
                <InputLabel>Runtime Cache</InputLabel>
                <Select
                  value={runtimeCache}
                  label="Runtime Cache"
                  onChange={(e) =>
                    setRuntimeCache(e.target.value as RuntimeCacheMode)
                  }
                >
                  <MenuItem value="content-addressed">
                    content-addressed
                  </MenuItem>
                  <MenuItem value="disabled">disabled</MenuItem>
                  <MenuItem value="forced">forced</MenuItem>
                </Select>
              </FormControl>
            </Stack>
          </Stack>
        </TabPanel>

        <TabPanel
          value={selectedTab}
          index={1}
          sx={{ flex: 1, overflow: "auto" }}
        >
          <Box sx={{ mt: "8px", px: 3 }}>
            <CodeBlock code={yamlPreview} language="yaml" />
          </Box>
        </TabPanel>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={
            saving ||
            !name.trim() ||
            !scenarios.some((s) => s.id.trim()) ||
            !datasetPath.trim() ||
            !nRuns.trim() ||
            !parallelScenarios.trim() ||
            !timeout.trim() ||
            !pauseBetweenRuns.trim()
          }
        >
          {saving ? "Saving..." : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
