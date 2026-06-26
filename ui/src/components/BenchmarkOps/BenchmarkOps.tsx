//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from "react";
import {
  Box,
  Button,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  analyzeBenchmark,
  exportBenchmark,
  importBenchmark,
  pollJob,
  type JobSubmitResponse,
} from "@/api/apiCalls";

interface BenchmarkOpsProps {
  library: string;
}

export function BenchmarkOps({ library }: BenchmarkOpsProps) {
  const [benchmarkId, setBenchmarkId] = useState("last");
  const [tarball, setTarball] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runJob = useCallback(
    async (label: string, submit: () => Promise<JobSubmitResponse>) => {
      setBusy(true);
      setStatus(`${label}: submitting…`);
      try {
        const { job_id } = await submit();
        setStatus(`${label}: job ${job_id} running…`);
        const result = await pollJob(job_id);
        setStatus(
          `${label}: ${result.status}${result.stderr ? ` — ${result.stderr.slice(0, 200)}` : ""}`,
        );
      } catch (err) {
        setStatus(
          `${label} failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  return (
    <Box
      sx={{
        p: 2,
        borderRadius: 1,
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Benchmark utilities
      </Typography>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 1 }}>
        <TextField
          size="small"
          label="Benchmark id"
          value={benchmarkId}
          onChange={(e) => setBenchmarkId(e.target.value)}
          helperText="short id, full id, last, or latest"
          sx={{ minWidth: 220 }}
        />
        <TextField
          size="small"
          label="Import tarball path"
          value={tarball}
          onChange={(e) => setTarball(e.target.value)}
          sx={{ flex: 1 }}
        />
      </Stack>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          variant="outlined"
          disabled={busy || !benchmarkId.trim()}
          onClick={() =>
            runJob("Analyze", () =>
              analyzeBenchmark(library, { benchmark_id: benchmarkId.trim() }),
            )
          }
        >
          Analyze
        </Button>
        <Button
          size="small"
          variant="outlined"
          disabled={busy || !benchmarkId.trim()}
          onClick={() =>
            runJob("Export", () =>
              exportBenchmark(library, { benchmark_id: benchmarkId.trim() }),
            )
          }
        >
          Export
        </Button>
        <Button
          size="small"
          variant="outlined"
          disabled={busy || !tarball.trim()}
          onClick={() =>
            runJob("Import", () =>
              importBenchmark(library, { tarball: tarball.trim() }),
            )
          }
        >
          Import
        </Button>
      </Stack>
      {status && (
        <Typography variant="caption" sx={{ display: "block", mt: 1, opacity: 0.85 }}>
          {status}
        </Typography>
      )}
    </Box>
  );
}
