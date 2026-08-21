//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useMemo } from "react";
import { Box, Paper, Stack, Typography } from "@mui/material";
import { Tooltip } from "@open-ui-kit/core";
import { HelpOutline as HelpIcon } from "@mui/icons-material";

import type { IocRunResults, IocBaselineMetric } from "@/api/apiCalls";
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from "@/common/styles";
import { iocTokens } from "@/theme/colors";
import {
  fmtPct,
  fmtDelta,
  deltaColor,
} from "@/components/IoCResultsHelpers/IoCResultsHelpers";

export interface IoCSignatureHeatmapProps {
  results: IocRunResults;
  onCellClick: (scenario: string, metric: string) => void;
  onRowClick: (scenario: string) => void;
  selectedScenario: string | null;
}

export function IoCSignatureHeatmap({
  results,
  onCellClick,
  onRowClick,
  selectedScenario,
}: IoCSignatureHeatmapProps) {
  const { metrics, challenges, baseline, confidence } = results;

  const baselineMap = useMemo(() => {
    const m: Record<string, IocBaselineMetric> = {};
    for (const b of baseline) m[b.metric] = b;
    return m;
  }, [baseline]);

  return (
    <Paper
      variant="outlined"
      sx={{ bgcolor: GLOBAL_BACKGROUND_COLOR, borderColor: GLOBAL_BORDER_COLOR }}
    >
      <Box sx={{ p: 1.5, borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}` }}>
        <Stack direction="row" sx={{ gap: 1, alignItems: "center" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            Failure-Rate Delta Heatmap
          </Typography>
          <Tooltip title={`Each cell shows failure-rate delta (overlay − baseline). Red = increased failures. Grey columns have saturated baselines (≥${Math.round(results.thresholds.saturated_at * 100)}%) — deltas there are non-diagnostic. Outlined cell = challenge's intended metric. Rates ±${Math.round(confidence.approx_band * 100)}%.`} placement="right">
            <HelpIcon sx={{ fontSize: 16, color: "text.secondary", cursor: "pointer" }} />
          </Tooltip>
        </Stack>
      </Box>

      <Box sx={{ overflowX: "auto" }}>
        <Box sx={{ display: "grid", gridTemplateColumns: `180px repeat(${metrics.length}, minmax(85px, 1fr))`, minWidth: metrics.length * 90 + 180 }}>
          {/* Header row: metric names */}
          <Box sx={{ p: 1, borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}` }} />
          {metrics.map((m) => {
            const bm = baselineMap[m];
            const isSat = bm?.saturated ?? false;
            return (
              <Tooltip key={m} title={isSat ? `Saturated: baseline rate ${fmtPct(bm?.rate ?? 0)} — deltas non-diagnostic` : m} placement="top">
                <Box
                  sx={{
                    p: 0.5,
                    borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}`,
                    textAlign: "center",
                    bgcolor: isSat ? iocTokens.saturatedBg : "transparent",
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      fontSize: 10,
                      writingMode: "vertical-rl",
                      textOrientation: "mixed",
                      display: "inline-block",
                      height: 80,
                      overflow: "hidden",
                      color: isSat ? "text.disabled" : "text.primary",
                    }}
                  >
                    {m}
                  </Typography>
                </Box>
              </Tooltip>
            );
          })}

          {/* Baseline strip row */}
          <Box
            sx={{
              p: 1,
              borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}`,
              display: "flex",
              alignItems: "center",
            }}
          >
            <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600 }}>
              Baseline rate
            </Typography>
          </Box>
          {metrics.map((m) => {
            const bm = baselineMap[m];
            const isSat = bm?.saturated ?? false;
            return (
              <Box
                key={m}
                sx={{
                  p: 0.5,
                  borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}`,
                  textAlign: "center",
                  bgcolor: isSat ? iocTokens.saturatedBg : "transparent",
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    fontFamily: "monospace",
                    fontSize: 11,
                    color: isSat ? "text.disabled" : "text.secondary",
                  }}
                >
                  {bm ? fmtPct(bm.rate) : "—"}
                </Typography>
              </Box>
            );
          })}

          {/* Challenge rows */}
          {challenges.map((ch) => {
            const perMetricMap: Record<string, (typeof ch.per_metric)[0]> = {};
            for (const pm of ch.per_metric) perMetricMap[pm.metric] = pm;
            const isSelected = ch.scenario === selectedScenario;

            return [
              <Box
                key={`${ch.scenario}-label`}
                onClick={() => onRowClick(ch.scenario)}
                sx={{
                  p: 1,
                  borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}`,
                  cursor: "pointer",
                  bgcolor: isSelected ? iocTokens.rowSelected : "transparent",
                  "&:hover": { bgcolor: iocTokens.rowHover },
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <Typography variant="caption" sx={{ fontWeight: 600, fontSize: 11 }}>
                  {ch.code}
                </Typography>
              </Box>,
              ...metrics.map((m) => {
                const pm = perMetricMap[m];
                const bm = baselineMap[m];
                const isSat = bm?.saturated ?? false;
                const isIntended = pm?.is_intended ?? false;
                const delta = pm?.delta ?? 0;

                return (
                  <Tooltip
                    key={`${ch.scenario}-${m}`}
                    title={
                      isSat
                        ? `${m}: saturated baseline (${fmtPct(bm?.rate ?? 0)}), delta non-diagnostic`
                        : `${m}: ${fmtPct(pm?.baseline_rate ?? 0)} → ${fmtPct(pm?.overlay_rate ?? 0)} (${fmtDelta(delta)})`
                    }
                    placement="top"
                  >
                    <Box
                      onClick={() => onCellClick(ch.scenario, m)}
                      sx={{
                        p: 0.5,
                        borderBottom: `1px solid ${GLOBAL_BORDER_COLOR}`,
                        textAlign: "center",
                        cursor: "pointer",
                        bgcolor: isSelected ? iocTokens.rowSelected : "transparent",
                        "&:hover": { bgcolor: iocTokens.cellHover },
                        position: "relative",
                      }}
                    >
                      <Box
                        sx={{
                          width: "100%",
                          height: 32,
                          borderRadius: 0.5,
                          bgcolor: isSat
                            ? iocTokens.saturatedBg
                            : deltaColor(delta, false),
                          border: isIntended ? "2px solid #fff" : "none",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          ...(isSat && {
                            backgroundImage: iocTokens.saturatedHatch,
                          }),
                        }}
                      >
                        {!isSat && delta !== 0 && (
                          <Typography
                            variant="caption"
                            sx={{
                              fontSize: 10,
                              fontFamily: "monospace",
                              color: "rgba(255,255,255,0.85)",
                            }}
                          >
                            {fmtDelta(delta)}
                          </Typography>
                        )}
                      </Box>
                    </Box>
                  </Tooltip>
                );
              }),
            ];
          })}
        </Box>
      </Box>
    </Paper>
  );
}
