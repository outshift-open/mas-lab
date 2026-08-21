//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Box, Paper, Stack, Typography } from "@mui/material";
import { Tooltip } from "@open-ui-kit/core";

import type { IocChallengeResult } from "@/api/apiCalls";
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from "@/common/styles";
import { iocTokens } from "@/theme/colors";
import {
  fmtPct,
  fmtDelta,
  VerdictBadge,
} from "@/components/IoCResultsHelpers/IoCResultsHelpers";

export interface IoCVerdictScorecardProps {
  challenges: IocChallengeResult[];
  confidence: { approx_band: number };
  onSelectChallenge: (scenario: string) => void;
  selectedScenario: string | null;
}

export function IoCVerdictScorecard({
  challenges,
  confidence,
  onSelectChallenge,
  selectedScenario,
}: IoCVerdictScorecardProps) {
  return (
    <Paper
      variant="outlined"
      sx={{ bgcolor: GLOBAL_BACKGROUND_COLOR, borderColor: GLOBAL_BORDER_COLOR }}
    >
      <Box sx={{ p: 1.5, borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}` }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          Reproduction Verdicts
        </Typography>
      </Box>

      {challenges.map((ch) => {
        const isSelected = ch.scenario === selectedScenario;
        return (
          <Box
            key={ch.scenario}
            onClick={() => onSelectChallenge(ch.scenario)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 2,
              px: 2,
              py: 1.5,
              cursor: "pointer",
              borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}`,
              bgcolor: isSelected ? iocTokens.rowSelected : "transparent",
              "&:hover": { bgcolor: iocTokens.rowHover },
              flexWrap: "wrap",
            }}
          >
            <Stack sx={{ minWidth: 180, flex: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {ch.code} {ch.display_name ?? ch.scenario}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {ch.intended_metric}
              </Typography>
            </Stack>

            <Stack direction="row" sx={{ gap: 1, alignItems: "center", minWidth: 200 }}>
              <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                {fmtPct(ch.intended.baseline_rate)} → {fmtPct(ch.intended.overlay_rate)}
              </Typography>
              <Tooltip title={`Delta: ${fmtDelta(ch.intended.delta)}. Rates are ±${Math.round(confidence.approx_band * 100)}%.`} placement="top">
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 700,
                    fontFamily: "monospace",
                    color: ch.intended.delta > 0
                      ? (ch.intended.saturated ? "text.secondary" : iocTokens.deltaPositive)
                      : "text.secondary",
                  }}
                >
                  {fmtDelta(ch.intended.delta)}
                </Typography>
              </Tooltip>
            </Stack>

            <VerdictBadge verdict={ch.verdict} />
          </Box>
        );
      })}
    </Paper>
  );
}
