//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  CircularProgress,
  Typography,
} from "@mui/material";

import { pollJob } from "@/api/apiCalls";

export interface ProgressViewProps {
  jobId: string;
}

export function ProgressView({ jobId }: ProgressViewProps) {
  const [status, setStatus] = useState("loading");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const job = await pollJob(jobId);
        if (!cancelled) {
          setStatus(job.status);
          if (job.status === "running") {
            setDetail("Run in progress…");
          } else if (job.status === "pending") {
            setDetail("Waiting to start…");
          }
        }
      } catch {
        if (!cancelled) setDetail("Unable to reach server.");
      }
    };
    check();
    const interval = setInterval(check, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 2 }}>
      <CircularProgress />
      <Typography variant="h6">{status === "pending" ? "Queued" : "Running"}</Typography>
      <Typography variant="body2" sx={{ color: "text.secondary" }}>{detail}</Typography>
      <Typography variant="caption" sx={{ color: "text.disabled" }}>Job: {jobId}</Typography>
    </Box>
  );
}

export interface ErrorViewProps {
  message: string;
  jobId: string;
}

export function ErrorView({ message, jobId }: ErrorViewProps) {
  return (
    <Box sx={{ py: 4 }}>
      <Alert severity="error" variant="outlined">
        <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
          Run did not produce results
        </Typography>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{message}</Typography>
        <Typography variant="caption" sx={{ display: "block", mt: 1, color: "text.secondary" }}>
          Job: {jobId}
        </Typography>
      </Alert>
    </Box>
  );
}
