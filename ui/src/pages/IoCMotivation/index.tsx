//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, Stack, Typography, useTheme } from "@mui/material";
import { Tabs, Tab } from "@open-ui-kit/core";
import { PageWithTitle, TabPanel, IoCRunsTable } from "@/components";
import type { IoCRunRow, IoCRunStatus } from "@/components/IoCRunsTable/IoCRunsTable";
import { useNavigate, useParams } from "react-router";
import {
  fetchJobs,
  fetchJobDetail,
  pollJob,
  cancelJob,
} from "@/api/apiCalls";

const TAB_KEYS = ["promptOverlay", "querySweep"] as const;
type TabKey = (typeof TAB_KEYS)[number];

const TAB_LABELS: Record<TabKey, string> = {
  promptOverlay: "Prompt Overlay",
  querySweep: "Query Sweep",
};

const POLL_INTERVAL = 3000;

const JOB_STATUS_TO_ROW_STATUS: Record<string, IoCRunStatus> = {
  pending: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Failed",
  timeout: "Failed",
  interrupted: "Failed",
};

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function jobToRow(
  job: {
    id: string;
    status: string;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    exit_code: number | null;
  },
  body?: Record<string, unknown>,
): IoCRunRow {
  const app = (body?.app as string) ?? "—";
  const overlays = (body?.overlays as string[]) ?? [];
  const reps = (body?.reps as number) ?? 0;
  const query = (body?.query as string) ?? undefined;
  const traceCount = (body?.trace_count as number) ?? reps * (overlays.length + 1);

  const status = JOB_STATUS_TO_ROW_STATUS[job.status] ?? "Failed";
  const isPartial =
    job.status === "completed" && job.exit_code === 1;

  return {
    id: job.id,
    status: isPartial ? "Partial" : status,
    progress:
      status === "Running" || status === "Queued"
        ? status
        : undefined,
    app,
    reps,
    probes: overlays.join(", ") || "—",
    started: formatTimestamp(job.started_at ?? job.created_at),
    duration: formatDuration(job.started_at, job.finished_at),
    reproduced: "—",
    traces: traceCount,
    query,
  };
}

const IoCMotivation = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { library = "" } = useParams<{ library: string }>();
  const [activeTab, setActiveTab] = useState(0);

  const [rows, setRows] = useState<IoCRunRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const pollTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const activeJobIds = useRef<Set<string>>(new Set());

  const updateRow = useCallback((row: IoCRunRow) => {
    setRows((prev) => {
      const idx = prev.findIndex((r) => r.id === row.id);
      if (idx === -1) return [row, ...prev];
      const next = [...prev];
      next[idx] = row;
      return next;
    });
  }, []);

  const startPolling = useCallback(
    (jobId: string, body?: Record<string, unknown>) => {
      if (pollTimers.current[jobId]) return;

      const poll = async () => {
        try {
          const job = await pollJob(jobId);
          const isTerminal =
            job.status === "completed" ||
            job.status === "failed" ||
            job.status === "cancelled" ||
            job.status === "timeout" ||
            job.status === "interrupted";

          const reqBody = (body ?? (job as unknown as { request_body?: Record<string, unknown> }).request_body) ?? {};
          updateRow(jobToRow(job, reqBody));

          if (isTerminal) {
            delete pollTimers.current[jobId];
            activeJobIds.current.delete(jobId);
          } else {
            pollTimers.current[jobId] = setTimeout(poll, POLL_INTERVAL);
          }
        } catch {
          delete pollTimers.current[jobId];
          activeJobIds.current.delete(jobId);
        }
      };

      activeJobIds.current.add(jobId);
      pollTimers.current[jobId] = setTimeout(poll, POLL_INTERVAL);
    },
    [updateRow],
  );

  useEffect(() => {
    const recoverJobs = async () => {
      setIsLoading(true);
      try {
        const allJobs = [
          ...(await fetchJobs("pending")),
          ...(await fetchJobs("running")),
          ...(await fetchJobs("completed")),
          ...(await fetchJobs("failed")),
        ];

        const iocJobs = allJobs
          .filter((j) => j.endpoint === "ioc/run")
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          );

        const recoveredRows: IoCRunRow[] = [];

        for (const job of iocJobs) {
          const detail = await fetchJobDetail(job.id);
          const body = detail.request_body ?? {};

          const row = jobToRow(
            { ...job, exit_code: detail.exit_code ?? null },
            body as Record<string, unknown>,
          );
          recoveredRows.push(row);

          const isTerminal =
            job.status === "completed" ||
            job.status === "failed" ||
            job.status === "cancelled" ||
            job.status === "timeout" ||
            job.status === "interrupted";

          if (!isTerminal && !pollTimers.current[job.id]) {
            startPolling(job.id, body as Record<string, unknown>);
          }
        }

        setRows(recoveredRows);
      } catch {
        /* server may be unreachable */
      } finally {
        setIsLoading(false);
      }
    };

    recoverJobs();

    return () => {
      for (const timer of Object.values(pollTimers.current)) {
        clearTimeout(timer);
      }
      pollTimers.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCancel = useCallback(
    async (jobId: string) => {
      try {
        await cancelJob(jobId);
        if (pollTimers.current[jobId]) {
          clearTimeout(pollTimers.current[jobId]);
          delete pollTimers.current[jobId];
        }
        const job = await pollJob(jobId);
        const detail = await fetchJobDetail(jobId);
        updateRow(
          jobToRow(job, (detail.request_body ?? {}) as Record<string, unknown>),
        );
      } catch {
        /* best effort */
      }
    },
    [updateRow],
  );

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  return (
    <PageWithTitle
      title={
        <Stack
          direction="row"
          sx={{ gap: "8px", justifyContent: "space-between", width: "100%" }}
        >
          <Typography
            variant="h5"
            sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}
          >
            IoC Motivation
          </Typography>
          <Button onClick={() => navigate(`/${library}/ioc-motivation/new`)}>
            New Run
          </Button>
        </Stack>
      }
    >
      <Box
        sx={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}
      >
        <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
          <Tabs value={activeTab} onChange={handleTabChange}>
            {TAB_KEYS.map((key, idx) => (
              <Tab
                key={key}
                label={TAB_LABELS[key]}
                id={`ioc-motivation-tab-${idx}`}
              />
            ))}
          </Tabs>
        </Box>

        <TabPanel value={activeTab} index={0} sx={{ flex: 1 }}>
          <Box sx={{ paddingTop: "8px" }}>
            <IoCRunsTable
              data={rows}
              isLoading={isLoading}
              onCancel={handleCancel}
              onViewReport={(id) => navigate(`/${library}/ioc-motivation/${id}`)}
            />
          </Box>
        </TabPanel>

        <TabPanel value={activeTab} index={1} sx={{ flex: 1 }}>
          <Typography variant="body1" sx={{ paddingTop: "8px" }}>
            Query Sweep content goes here.
          </Typography>
        </TabPanel>
      </Box>
    </PageWithTitle>
  );
};

export default IoCMotivation;
