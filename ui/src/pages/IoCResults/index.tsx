//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useCallback, useMemo, useState } from "react";
import {
  Box,
  CircularProgress,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import { useNavigate, useParams } from "react-router";

import { PageWithTitle } from "@/components";
import { ApiError, useIocRunResults } from "@/api/apiCalls";
import { IoCRunHeader } from "@/components/IoCRunHeader/IoCRunHeader";
import { IoCVerdictScorecard } from "@/components/IoCVerdictScorecard/IoCVerdictScorecard";
import { IoCSignatureHeatmap } from "@/components/IoCSignatureHeatmap/IoCSignatureHeatmap";
import { IoCChallengeDetail } from "@/components/IoCChallengeDetail/IoCChallengeDetail";
import { IoCBaselineNoiseFloor } from "@/components/IoCBaselineNoiseFloor/IoCBaselineNoiseFloor";
import { ProgressView, ErrorView } from "@/components/IoCResultsStatus/IoCResultsStatus";

const IoCResults = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { library = "", jobId = "" } = useParams<{ library: string; jobId: string }>();

  const { data: results, isLoading, error } = useIocRunResults(jobId);
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);

  const apiError = error instanceof ApiError ? error : null;
  const isRunning = apiError?.status === 202;
  const isFailed = apiError?.status === 422;

  const effectiveScenario = selectedScenario ?? results?.challenges[0]?.scenario ?? null;

  const selectedChallenge = useMemo(
    () => results?.challenges.find((ch) => ch.scenario === effectiveScenario) ?? null,
    [results, effectiveScenario],
  );

  const handleCellClick = useCallback(
    (scenario: string, _metric: string) => {
      setSelectedScenario(scenario);
    },
    [],
  );

  const titleText = (
    <Typography variant="h5" sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}>
      IoC Run Results
    </Typography>
  );

  if (isLoading) {
    return (
      <PageWithTitle title={titleText}>
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      </PageWithTitle>
    );
  }

  if (isRunning) {
    return (
      <PageWithTitle title={titleText}>
        <ProgressView jobId={jobId} />
      </PageWithTitle>
    );
  }

  if (isFailed || (error && !results)) {
    return (
      <PageWithTitle title={titleText}>
        <ErrorView
          message={(error as Error)?.message ?? "No results available"}
          jobId={jobId}
        />
      </PageWithTitle>
    );
  }

  if (!results) {
    return (
      <PageWithTitle title={titleText}>
        <ErrorView message="No results available" jobId={jobId} />
      </PageWithTitle>
    );
  }

  return (
    <PageWithTitle
      title={
        <Stack direction="row" sx={{ gap: 1, alignItems: "center", width: "100%" }}>
          <Typography
            variant="h5"
            sx={{
              color: theme.palette.vars.interactivePrimaryDefaultDefault,
              cursor: "pointer",
              "&:hover": { textDecoration: "underline" },
            }}
            onClick={() => navigate(`/${library}/ioc-motivation`)}
          >
            IoC Motivation
          </Typography>
          <Typography variant="h5" sx={{ color: "text.disabled" }}>/</Typography>
          <Typography variant="h5" sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}>
            Results
          </Typography>
        </Stack>
      }
    >
      <Stack sx={{ gap: 2, pb: 4 }}>
        <IoCRunHeader results={results} />

        <IoCVerdictScorecard
          challenges={results.challenges}
          confidence={results.confidence}
          onSelectChallenge={setSelectedScenario}
          selectedScenario={effectiveScenario}
        />

        <IoCSignatureHeatmap
          results={results}
          onCellClick={handleCellClick}
          onRowClick={setSelectedScenario}
          selectedScenario={effectiveScenario}
        />

        {selectedChallenge && (
          <IoCChallengeDetail
            challenge={selectedChallenge}
            confidence={results.confidence}
            jobId={jobId}
          />
        )}

        <IoCBaselineNoiseFloor
          baseline={results.baseline}
          saturatedAt={results.thresholds.saturated_at}
        />
      </Stack>
    </PageWithTitle>
  );
};

export default IoCResults;
