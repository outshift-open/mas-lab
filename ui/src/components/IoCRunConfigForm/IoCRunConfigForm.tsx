//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
} from "@mui/material";
import {
  Stack,
  Typography,
  Tooltip,
  Tabs,
  Tab,
  DropdownAutocompleteTree,
  useDropdownAutocompleteTree,
} from "@open-ui-kit/core";
import type { SelectNodeType } from "@open-ui-kit/core";
import InfoOutlineIcon from "@mui/icons-material/InfoOutlined";
import { CodeBlock, TabPanel } from "@/components";
import { useIocCatalog } from "@/api/apiCalls";
import type { IocApp } from "@/api/apiCalls";
import { stringify } from "yaml";

const COST_PER_TRACE = 0.2;
const MINUTES_PER_TRACE_LOW = 1;
const MINUTES_PER_TRACE_HIGH = 2;

export interface IoCRunConfig {
  app: string;
  selectedOverlays: Array<{
    challengeCode: string;
    overlayId: string;
    overlayPath: string;
  }>;
  query: string;
  reps: number;
}

export interface IoCRunConfigFormProps {
  library: string;
  onSubmit: (config: IoCRunConfig) => void | Promise<void>;
  onCancel: () => void;
}

function buildChallengeOverlayTree(appData: IocApp): SelectNodeType[] {
  return appData.challenges.map((challenge) => ({
    value: `${challenge.code} · ${challenge.intended_metric}`,
    isSelectable: true,
    childNodes: challenge.overlays.map((ov) => ({
      value: ov.name,
      isSelectable: true,
      linkedData: {
        challengeCode: challenge.code,
        overlayId: ov.id,
        overlayPath: ov.overlay,
      },
    })),
  }));
}

export const IoCRunConfigForm = ({
  library: _library,
  onSubmit,
  onCancel,
}: IoCRunConfigFormProps) => {
  void _library;
  const { data: catalog, isLoading, error: catalogError } = useIocCatalog();

  const appIds = useMemo(
    () => (catalog ? Object.keys(catalog.apps) : []),
    [catalog],
  );

  const [app, setApp] = useState("");
  const [query, setQuery] = useState("");
  const [reps, setReps] = useState("5");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [selectedTab, setSelectedTab] = useState(0);

  useEffect(() => {
    if (appIds.length > 0 && !app) {
      setApp(appIds[0]);
    }
  }, [appIds, app]);

  const currentApp: IocApp | undefined = catalog?.apps[app];

  const treeData = useMemo(
    () => (currentApp ? buildChallengeOverlayTree(currentApp) : []),
    [currentApp],
  );

  const {
    flattenedTreeOptions,
    onSelectAllChange,
    searchTextDebounced,
    selectAllNode,
    selectedValues,
    setSearchText,
    toggleExpand,
    updateCheckbox,
  } = useDropdownAutocompleteTree({
    parentSelectOnly: false,
    selectAllIcon: null,
    treeData,
  });

  useEffect(() => {
    if (currentApp) {
      setQuery(currentApp.default_query);
    }
    updateCheckbox(treeData, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app]);

  const selectedOverlays = useMemo(
    () =>
      selectedValues
        .filter((v) => v.linkedData)
        .map(
          (v) =>
            v.linkedData as {
              challengeCode: string;
              overlayId: string;
              overlayPath: string;
            },
        ),
    [selectedValues],
  );

  const overlayCount = selectedOverlays.length;
  const parsedReps = parseInt(reps, 10) || 0;
  const totalTraces = parsedReps * (overlayCount + (overlayCount > 0 ? 1 : 0));

  const buttonLabel = useMemo(() => {
    if (overlayCount === 0) return "Select challenges & overlays *";
    const challengeCodes = [
      ...new Set(selectedOverlays.map((o) => o.challengeCode)),
    ];
    return `${challengeCodes.join(", ")} · ${overlayCount} overlay${overlayCount !== 1 ? "s" : ""}`;
  }, [overlayCount, selectedOverlays]);

  const buildConfigSummary = (): Record<string, unknown> => ({
    app,
    overlays: selectedOverlays.map((o) => ({
      challenge: o.challengeCode,
      overlay_id: o.overlayId,
      overlay: o.overlayPath,
    })),
    query: query.trim() || undefined,
    reps: parsedReps || 5,
    baseline: "matched (no overlay, same app + query)",
  });

  const yamlPreview = useMemo(
    () => stringify(buildConfigSummary(), { lineWidth: 120 }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [app, selectedOverlays, query, reps],
  );

  const handleSubmit = async () => {
    setError("");

    if (overlayCount === 0) {
      setError("Select at least one overlay.");
      return;
    }
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setError("Enter a query.");
      return;
    }
    if (!parsedReps || parsedReps < 1) {
      setError("Reps must be at least 1.");
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit({
        app,
        selectedOverlays,
        query: trimmedQuery,
        reps: parsedReps,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run.");
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit =
    !submitting && overlayCount > 0 && !!query.trim() && parsedReps >= 1;

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (catalogError) {
    return (
      <Alert severity="error" sx={{ m: 2 }}>
        Failed to load IoC catalog:{" "}
        {catalogError instanceof Error
          ? catalogError.message
          : "Unknown error"}
        . Ensure <code>IOC_REPO</code> is set on the server.
      </Alert>
    );
  }

  return (
    <Box
      sx={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}
    >
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Tabs value={selectedTab} onChange={(_, v) => setSelectedTab(v)}>
          <Tab label="Configure" id="ioc-run-config-tab-0" />
          <Tab label="Summary" id="ioc-run-config-tab-1" />
        </Tabs>
      </Box>

      <TabPanel
        value={selectedTab}
        index={0}
        sx={{ flex: 1, overflow: "auto" }}
      >
        <Stack sx={{ gap: "20px", maxWidth: 720 }}>
          {error && <Alert severity="error">{error}</Alert>}

          <FormControl variant="standard" fullWidth>
            <InputLabel>
              <Stack direction="row" sx={{ alignItems: "center", gap: "4px" }}>
                App *
                <Tooltip
                  title="The multi-agent system under test. Apps with a clean baseline are preferred testbeds."
                  placement="top"
                  sx={{ maxWidth: "400px" }}
                >
                  <InfoOutlineIcon
                    sx={{ width: "14px", height: "14px", cursor: "pointer" }}
                  />
                </Tooltip>
              </Stack>
            </InputLabel>
            <Select
              value={app}
              label="App"
              onChange={(e) => setApp(e.target.value)}
            >
              {appIds.map((id) => {
                const a = catalog!.apps[id];
                return (
                  <MenuItem key={id} value={id}>
                    <Stack>
                      <Typography variant="body2">{a.display_name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {a.description}
                      </Typography>
                    </Stack>
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>

          {currentApp && !currentApp.baseline_clean && (
            <Alert severity="warning">
              {currentApp.display_name} has a loaded baseline — several metrics
              are saturated and non-diagnostic. Deltas are only meaningful where
              headroom exists.
            </Alert>
          )}

          <Stack sx={{ gap: "6px" }}>
            <Stack direction="row" sx={{ alignItems: "center", gap: "4px" }}>
              <Typography variant="caption" color="text.secondary">
                Challenges & Overlays *
              </Typography>
              <Tooltip
                title="Select one or more overlays grouped by challenge. Each challenge is a cognitive-failure mode; its overlays inject the fault into the agent(s). The tree supports multi-select across challenges."
                placement="top"
                sx={{ maxWidth: "400px" }}
              >
                <InfoOutlineIcon
                  sx={{ width: "14px", height: "14px", cursor: "pointer" }}
                />
              </Tooltip>
            </Stack>
            <DropdownAutocompleteTree
              buttonContent={buttonLabel}
              flattenedTreeOptions={
                flattenedTreeOptions.flattenedSelectTreeWithSearch
              }
              isIconAllowed={false}
              isSearchFieldEnabled
              onSelectAllChange={onSelectAllChange}
              parentSelectOnly={false}
              searchText={searchTextDebounced}
              selectAllNode={selectAllNode}
              setSearchText={setSearchText}
              toggleExpand={toggleExpand}
              updateCheckbox={updateCheckbox}
              buttonProps={{ fullWidth: true }}
            />
          </Stack>

          <TextField
            label={
              <Stack direction="row" sx={{ alignItems: "center", gap: "4px" }}>
                Query *
                <Tooltip
                  title="The user query for the run. The same query is used for both the challenge run(s) and the matched baseline, ensuring a fair comparison."
                  placement="top"
                  sx={{ maxWidth: "400px" }}
                >
                  <InfoOutlineIcon
                    sx={{ width: "14px", height: "14px", cursor: "pointer" }}
                  />
                </Tooltip>
              </Stack>
            }
            placeholder="Enter the user query for the run"
            variant="standard"
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            multiline
            rows={3}
            fullWidth
            helperText="The same query is used for the challenge(s) and the matched baseline."
          />

          <TextField
            label={
              <Stack direction="row" sx={{ alignItems: "center", gap: "4px" }}>
                Reps (N) *
                <Tooltip
                  title="Number of independent repetitions (N). Each rep produces a challenge + baseline trace pair per overlay. N=1 is a smoke test only — single-run conclusions are unreliable. N≥5 is recommended."
                  placement="top"
                  sx={{ maxWidth: "400px" }}
                >
                  <InfoOutlineIcon
                    sx={{ width: "14px", height: "14px", cursor: "pointer" }}
                  />
                </Tooltip>
              </Stack>
            }
            variant="standard"
            autoComplete="off"
            value={reps}
            onChange={(e) => {
              const val = parseInt(e.target.value, 10);
              if (e.target.value === "" || (val >= 0 && val <= 10)) {
                setReps(e.target.value);
              }
            }}
            type="number"
            slotProps={{ htmlInput: { min: 1, max: 10 } }}
            sx={{ width: 120 }}
            helperText={
              parsedReps === 1
                ? "Smoke test only — rates are unreliable at N=1."
                : undefined
            }
          />

          {parsedReps === 1 && (
            <Alert severity="info">
              N=1 is unreliable and actively misleading — single-run conclusions
              were reversed at N=5. Consider using N=5 or higher.
            </Alert>
          )}

          {totalTraces > 0 && (
            <Typography variant="body2" color="text.secondary">
              Estimated: {totalTraces} traces ({overlayCount} overlay
              {overlayCount !== 1 ? "s" : ""} + 1 baseline) × {parsedReps} reps
              &nbsp;≈&nbsp;${(totalTraces * COST_PER_TRACE).toFixed(2)}{" "}
              &nbsp;·&nbsp;
              {totalTraces * MINUTES_PER_TRACE_LOW}–
              {totalTraces * MINUTES_PER_TRACE_HIGH} min
            </Typography>
          )}
        </Stack>
      </TabPanel>

      <TabPanel
        value={selectedTab}
        index={1}
        sx={{ flex: 1, overflow: "auto" }}
      >
        <Box sx={{ maxWidth: 720 }}>
          <CodeBlock code={yamlPreview} language="yaml" />
        </Box>
      </TabPanel>

      <Divider sx={{ mt: 3 }} />

      <Stack
        direction="row"
        sx={{ gap: "12px", justifyContent: "flex-end", pt: 2, pb: 1 }}
      >
        <Button onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="primary" onClick={handleSubmit} disabled={!canSubmit}>
          {submitting ? "Starting…" : "Start Run"}
        </Button>
      </Stack>
    </Box>
  );
};
