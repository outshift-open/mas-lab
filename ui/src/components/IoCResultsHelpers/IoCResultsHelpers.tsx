//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Chip } from "@mui/material";
import { Tooltip } from "@open-ui-kit/core";
import {
  CheckCircle as CheckCircleIcon,
  RadioButtonUnchecked as EmptyCircleIcon,
  HelpOutline as HelpIcon,
} from "@mui/icons-material";

import { iocTokens } from "@/theme/colors";

export const VERDICT_CONFIG: Record<
  string,
  { label: string; color: string; icon: "full" | "half" | "empty" }
> = {
  reproduced: { label: "Reproduced", color: iocTokens.verdictReproduced, icon: "full" },
  reproduced_low_confidence: { label: "Reproduced (low-confidence)", color: iocTokens.verdictLowConfidence, icon: "half" },
  saturated: { label: "Saturated — see footprint", color: iocTokens.verdictNeutral, icon: "empty" },
  no_signal: { label: "No signal", color: iocTokens.verdictNeutral, icon: "empty" },
  unknown: { label: "Unknown", color: iocTokens.verdictNeutral, icon: "empty" },
};

export function fmtPct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export function fmtDelta(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${Math.round(v * 100)}%`;
}

export function fmtCost(v: number | null): string {
  if (v == null) return "—";
  return v < 1 ? `$${v.toFixed(2)}` : `~$${Math.round(v)}`;
}

export function fmtModel(m: string | undefined): string {
  if (!m) return "—";
  const parts = m.split("/");
  return parts[parts.length - 1];
}

export function fmtTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function deltaColor(delta: number, saturated: boolean): string {
  if (saturated) return "transparent";
  if (delta <= 0) return "transparent";
  const intensity = Math.min(delta / 0.8, 1);
  return `rgba(244, 67, 54, ${0.15 + intensity * 0.65})`;
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const cfg = VERDICT_CONFIG[verdict] ?? VERDICT_CONFIG.unknown;
  const Icon =
    cfg.icon === "full" ? CheckCircleIcon :
    cfg.icon === "half" ? HelpIcon : EmptyCircleIcon;
  return (
    <Chip
      icon={<Icon sx={{ fontSize: 16, color: `${cfg.color} !important` }} />}
      label={cfg.label}
      size="small"
      variant="outlined"
      sx={{ borderColor: cfg.color, color: cfg.color, fontWeight: 500 }}
    />
  );
}

export function ConfidenceBadge({ reps, band }: { reps: number; band: number }) {
  return (
    <Tooltip title={`With N=${reps} reps, failure rates have an approximate margin of ±${Math.round(band * 100)}%. Increase N for tighter confidence.`} placement="bottom">
      <Chip
        label={`N=${reps} · rates ±${Math.round(band * 100)}%`}
        size="small"
        variant="outlined"
        sx={{ borderColor: iocTokens.verdictLowConfidence, color: iocTokens.verdictLowConfidence, fontWeight: 500 }}
      />
    </Tooltip>
  );
}
