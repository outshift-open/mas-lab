//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import {
  Box,
  Chip,
  CircularProgress,
  Collapse,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { Tooltip } from "@open-ui-kit/core";

import {
  useIocRunEvidence,
  type IocChallengeResult,
} from "@/api/apiCalls";
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from "@/common/styles";
import { iocTokens } from "@/theme/colors";
import {
  fmtPct,
  fmtDelta,
  VerdictBadge,
} from "@/components/IoCResultsHelpers/IoCResultsHelpers";

export interface IoCChallengeDetailProps {
  challenge: IocChallengeResult;
  confidence: { approx_band: number };
  jobId: string;
}

export function IoCChallengeDetail({
  challenge,
  confidence,
  jobId,
}: IoCChallengeDetailProps) {
  const [evidenceMetric, setEvidenceMetric] = useState<string | null>(null);

  const {
    data: evidence,
    isLoading: evidenceLoading,
  } = useIocRunEvidence(jobId, challenge.scenario, evidenceMetric);

  const toggleEvidence = (metric: string) => {
    setEvidenceMetric((prev) => (prev === metric ? null : metric));
  };

  const maxRate = useMemo(
    () => Math.max(...challenge.per_metric.map((pm) => Math.max(pm.baseline_rate, pm.overlay_rate)), 0.01),
    [challenge.per_metric],
  );

  return (
    <Paper
      variant="outlined"
      sx={{ bgcolor: GLOBAL_BACKGROUND_COLOR, borderColor: GLOBAL_BORDER_COLOR }}
    >
      <Box sx={{ p: 1.5, borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}` }}>
        <Stack direction="row" sx={{ gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            {challenge.code} {challenge.display_name ?? challenge.scenario}
          </Typography>
          <VerdictBadge verdict={challenge.verdict} />
        </Stack>
      </Box>

      {/* Footprint chips */}
      {challenge.footprint.length > 0 && (
        <Box sx={{ px: 2, py: 1, borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}` }}>
          <Typography variant="caption" sx={{ color: "text.secondary", mr: 1 }}>
            Footprint:
          </Typography>
          {challenge.footprint.map((f) => (
            <Chip
              key={f.metric}
              label={`${f.metric} ${fmtDelta(f.delta)}`}
              size="small"
              sx={{
                mr: 0.5,
                mb: 0.5,
                bgcolor: iocTokens.footprintBg,
                color: iocTokens.failText,
                fontFamily: "monospace",
                fontSize: 11,
              }}
            />
          ))}
        </Box>
      )}

      {/* Grouped bars: baseline vs overlay per metric */}
      <Box sx={{ px: 2, py: 1.5, overflowX: "auto" }}>
        {challenge.per_metric.map((pm) => {
          const isSat = pm.saturated;
          const isIntended = pm.is_intended;
          const isEvidenceOpen = pm.metric === evidenceMetric;

          return (
            <Box key={pm.metric} sx={{ mb: 0.5 }}>
              <Box
                onClick={() => toggleEvidence(pm.metric)}
                sx={{ display: "flex", alignItems: "center", gap: 1, cursor: "pointer", "&:hover": { bgcolor: iocTokens.rowSelected }, py: 0.5, px: 0.5, borderRadius: 0.5 }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    minWidth: 150,
                    maxWidth: 150,
                    fontWeight: isIntended ? 700 : 400,
                    color: isSat ? "text.disabled" : "text.primary",
                    textDecoration: isIntended ? "underline" : "none",
                    fontSize: 11,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {pm.metric}
                </Typography>

                <Box sx={{ flex: 1, minWidth: 150, display: "flex", flexDirection: "column", gap: "2px" }}>
                  {/* Baseline bar */}
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                    <Box
                      sx={{
                        height: 10,
                        width: `${Math.max((pm.baseline_rate / maxRate) * 100, 1)}%`,
                        maxWidth: "100%",
                        bgcolor: isSat ? iocTokens.saturatedBar : iocTokens.baselineBar,
                        borderRadius: 0.5,
                      }}
                    />
                    <Typography variant="caption" sx={{ fontSize: 9, color: "text.secondary", fontFamily: "monospace", minWidth: 30 }}>
                      {fmtPct(pm.baseline_rate)}
                    </Typography>
                  </Box>
                  {/* Overlay bar */}
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                    <Box
                      sx={{
                        height: 10,
                        width: `${Math.max((pm.overlay_rate / maxRate) * 100, 1)}%`,
                        maxWidth: "100%",
                        bgcolor: isSat ? iocTokens.saturatedBar : iocTokens.overlayBar,
                        borderRadius: 0.5,
                      }}
                    />
                    <Typography variant="caption" sx={{ fontSize: 9, color: "text.secondary", fontFamily: "monospace", minWidth: 30 }}>
                      {fmtPct(pm.overlay_rate)}
                    </Typography>
                  </Box>
                </Box>

                <Tooltip title={`Delta: ${fmtDelta(pm.delta)} (±${Math.round(confidence.approx_band * 100)}%)`} placement="top">
                  <Typography
                    variant="caption"
                    sx={{
                      fontFamily: "monospace",
                      fontWeight: 700,
                      minWidth: 50,
                      textAlign: "right",
                      color: isSat ? "text.disabled" : (pm.delta > 0 ? iocTokens.deltaPositive : "text.secondary"),
                    }}
                  >
                    {isSat ? "sat." : fmtDelta(pm.delta)}
                  </Typography>
                </Tooltip>
              </Box>

              {/* Evidence panel */}
              <Collapse in={isEvidenceOpen && !evidenceLoading && evidence != null}>
                {evidence && isEvidenceOpen && (
                  <Box sx={{ ml: 4, mb: 1, pl: 2, borderLeft: `2px solid ${GLOBAL_BORDER_COLOR}` }}>
                    <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, mb: 0.5, display: "block" }}>
                      Per-rep evidence ({evidence.reps.length} reps)
                    </Typography>
                    {evidence.reps.map((rep) => (
                      <Box
                        key={rep.rep}
                        sx={{
                          mb: 1,
                          p: 1,
                          borderRadius: 1,
                          bgcolor: rep.failed ? iocTokens.failBg : iocTokens.passBg,
                          border: `1px solid ${rep.failed ? iocTokens.failBorder : iocTokens.passBorder}`,
                        }}
                      >
                        <Stack direction="row" sx={{ gap: 1, alignItems: "center", mb: 0.5 }}>
                          <Typography variant="caption" sx={{ fontWeight: 600 }}>
                            Rep {rep.rep}
                          </Typography>
                          <Chip
                            label={rep.failed ? "FAIL" : "PASS"}
                            size="small"
                            sx={{
                              height: 18,
                              fontSize: 10,
                              bgcolor: rep.failed ? iocTokens.failBorder : iocTokens.passBorder,
                              color: rep.failed ? iocTokens.failText : iocTokens.passText,
                            }}
                          />
                          {rep.fatal_failures > 0 && (
                            <Typography variant="caption" sx={{ color: iocTokens.failText }}>
                              {rep.fatal_failures} fatal
                            </Typography>
                          )}
                        </Stack>
                        <Typography
                          variant="caption"
                          sx={{
                            color: "text.secondary",
                            display: "block",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            fontSize: 11,
                            lineHeight: 1.5,
                          }}
                        >
                          {rep.reasoning || "(no reasoning provided)"}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                )}
              </Collapse>

              {isEvidenceOpen && evidenceLoading && (
                <Box sx={{ ml: 4, py: 1 }}>
                  <CircularProgress size={16} />
                </Box>
              )}
            </Box>
          );
        })}
      </Box>

      <Box sx={{ px: 2, pb: 1 }}>
        <Stack direction="row" sx={{ gap: 2, alignItems: "center" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Box sx={{ width: 12, height: 10, bgcolor: iocTokens.baselineBar, borderRadius: 0.5 }} />
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10 }}>Baseline</Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Box sx={{ width: 12, height: 10, bgcolor: iocTokens.overlayBar, borderRadius: 0.5 }} />
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10 }}>Overlay</Typography>
          </Box>
          <Typography variant="caption" sx={{ color: "text.disabled", fontSize: 10 }}>
            Click any metric row for judge evidence
          </Typography>
        </Stack>
      </Box>
    </Paper>
  );
}
