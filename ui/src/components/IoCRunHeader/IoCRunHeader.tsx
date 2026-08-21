//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import { Tooltip } from "@open-ui-kit/core";

import type { IocRunResults } from "@/api/apiCalls";
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from "@/common/styles";
import {
  fmtCost,
  fmtModel,
  fmtTimestamp,
  ConfidenceBadge,
} from "@/components/IoCResultsHelpers/IoCResultsHelpers";

export interface IoCRunHeaderProps {
  results: IocRunResults;
}

export function IoCRunHeader({ results }: IoCRunHeaderProps) {
  const { run, confidence } = results;
  const [queryExpanded, setQueryExpanded] = useState(false);

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        bgcolor: GLOBAL_BACKGROUND_COLOR,
        borderColor: GLOBAL_BORDER_COLOR,
      }}
    >
      <Stack direction="row" sx={{ flexWrap: "wrap", gap: 2, alignItems: "center" }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          {run.app_display_name}
        </Typography>
        <Chip label={`N=${run.reps}`} size="small" variant="outlined" />
        <Tooltip title={`Agents: ${run.models.agents ?? "—"} · Judge: ${run.models.judge ?? "—"}`} placement="bottom">
          <Chip label={fmtModel(run.models.agents)} size="small" variant="outlined" />
        </Tooltip>
        <Chip label={`${run.traces ?? "?"} traces`} size="small" variant="outlined" />
        <Chip label={fmtCost(run.cost_usd)} size="small" variant="outlined" />
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          {fmtTimestamp(run.finished_at)}
        </Typography>
        <ConfidenceBadge reps={confidence.reps} band={confidence.approx_band} />
      </Stack>

      {run.query && (
        <Box sx={{ mt: 1 }}>
          <Typography
            variant="body2"
            sx={{
              color: "text.secondary",
              cursor: "pointer",
              overflow: queryExpanded ? "visible" : "hidden",
              textOverflow: queryExpanded ? "unset" : "ellipsis",
              whiteSpace: queryExpanded ? "normal" : "nowrap",
              maxWidth: queryExpanded ? "none" : 600,
            }}
            onClick={() => setQueryExpanded(!queryExpanded)}
          >
            <strong>Query:</strong> {run.query}
          </Typography>
        </Box>
      )}
    </Paper>
  );
}
