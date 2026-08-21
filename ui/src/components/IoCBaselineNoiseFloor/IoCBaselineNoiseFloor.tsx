//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import {
  Box,
  Collapse,
  IconButton,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { Tooltip } from "@open-ui-kit/core";
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  HelpOutline as HelpIcon,
} from "@mui/icons-material";

import type { IocBaselineMetric } from "@/api/apiCalls";
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from "@/common/styles";
import { iocTokens } from "@/theme/colors";
import { fmtPct } from "@/components/IoCResultsHelpers/IoCResultsHelpers";

export interface IoCBaselineNoiseFloorProps {
  baseline: IocBaselineMetric[];
  saturatedAt: number;
}

export function IoCBaselineNoiseFloor({
  baseline,
  saturatedAt,
}: IoCBaselineNoiseFloorProps) {
  const [expanded, setExpanded] = useState(false);
  const clean = baseline.filter((b) => !b.saturated);
  const saturated = baseline.filter((b) => b.saturated);

  return (
    <Paper
      variant="outlined"
      sx={{ bgcolor: GLOBAL_BACKGROUND_COLOR, borderColor: GLOBAL_BORDER_COLOR }}
    >
      <Box
        onClick={() => setExpanded(!expanded)}
        sx={{
          p: 1.5,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Stack direction="row" sx={{ gap: 1, alignItems: "center" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            Baseline Noise Floor
          </Typography>
          <Tooltip title={`Metrics with baseline failure rate ≥${Math.round(saturatedAt * 100)}% are saturated: the app already fails them without any overlay, so overlay deltas there are non-diagnostic.`} placement="right">
            <HelpIcon sx={{ fontSize: 16, color: "text.secondary", cursor: "pointer" }} />
          </Tooltip>
        </Stack>
        <IconButton size="small">
          {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        </IconButton>
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ px: 2, pb: 2 }}>
          {clean.length > 0 && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" sx={{ color: iocTokens.verdictReproduced, fontWeight: 600, mb: 0.5, display: "block" }}>
                Clean — headroom for overlay signal ({clean.length})
              </Typography>
              {clean.map((b) => (
                <Box key={b.metric} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.25 }}>
                  <Typography variant="caption" sx={{ minWidth: 180, fontSize: 11 }}>{b.metric}</Typography>
                  <Box sx={{ flex: 1, maxWidth: 200 }}>
                    <Box sx={{ height: 8, width: `${Math.max(b.rate * 100, 1)}%`, bgcolor: iocTokens.cleanBar, borderRadius: 0.5 }} />
                  </Box>
                  <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: 11, minWidth: 40, textAlign: "right" }}>
                    {fmtPct(b.rate)}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}

          {saturated.length > 0 && (
            <Box>
              <Typography variant="caption" sx={{ color: iocTokens.verdictNeutral, fontWeight: 600, mb: 0.5, display: "block" }}>
                Saturated — non-diagnostic ({saturated.length})
              </Typography>
              {saturated.map((b) => (
                <Box key={b.metric} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.25 }}>
                  <Typography variant="caption" sx={{ minWidth: 180, fontSize: 11, color: "text.disabled" }}>{b.metric}</Typography>
                  <Box sx={{ flex: 1, maxWidth: 200 }}>
                    <Box sx={{ height: 8, width: `${Math.max(b.rate * 100, 1)}%`, bgcolor: iocTokens.saturatedBar, borderRadius: 0.5 }} />
                  </Box>
                  <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: 11, minWidth: 40, textAlign: "right", color: "text.disabled" }}>
                    {fmtPct(b.rate)}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      </Collapse>
    </Paper>
  );
}
