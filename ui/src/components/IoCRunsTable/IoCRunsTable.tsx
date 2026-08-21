//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import {
  MaterialReactTable,
  MRT_SortingState,
  MRT_VisibilityState,
} from "material-react-table";
import {
  CreateTableInstance,
  EmptyState,
  TableProps,
  Tooltip,
} from "@open-ui-kit/core";
import { useMemo, useState } from "react";
import { Button, Chip, Stack, Typography } from "@mui/material";
import { GLOBAL_BACKGROUND_COLOR } from "@/common/styles";

export type IoCRunStatus =
  | "Queued"
  | "Running"
  | "Completed"
  | "Failed"
  | "Partial";

export interface IoCRunRow {
  id: string;
  status: IoCRunStatus;
  progress?: string;
  app: string;
  reps: number;
  probes: string;
  started: string;
  duration: string;
  reproduced: string;
  traces?: number;
  cost?: string;
  agentModel?: string;
  failures?: number;
  query?: string;
}

const STATUS_COLOR: Record<IoCRunStatus, string> = {
  Queued: "text.secondary",
  Running: "primary.main",
  Completed: "success.main",
  Failed: "error.main",
  Partial: "warning.main",
};

type ColumnDefs = TableProps<IoCRunRow>["columns"];

export interface IoCRunsTableProps {
  data: IoCRunRow[];
  isLoading?: boolean;
  onViewReport?: (id: string) => void;
  onOpenBundle?: (id: string) => void;
  onCancel?: (id: string) => void;
  onReRun?: (id: string) => void;
}

export const IoCRunsTable = ({
  data,
  isLoading = false,
  onViewReport,
  onOpenBundle,
  onCancel,
  onReRun,
}: IoCRunsTableProps) => {
  const [columnVisibility, setColumnVisibility] = useState<MRT_VisibilityState>(
    {
      traces: false,
      cost: false,
      agentModel: false,
      failures: false,
      query: false,
    },
  );
  const [sorting, setSorting] = useState<MRT_SortingState>([
    { id: "started", desc: true },
  ]);

  const columns = useMemo<ColumnDefs>(
    () => [
      {
        accessorKey: "id",
        header: "Run ID / Name",
        size: 260,
        accessorFn: (row) => (
          <Tooltip title={row.id} placement="top">
            <Typography
              variant="body2"
              sx={{
                textOverflow: "ellipsis",
                overflow: "hidden",
                whiteSpace: "nowrap",
              }}
            >
              {row.id}
            </Typography>
          </Tooltip>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        size: 110,
        accessorFn: (row) => (
          <Typography
            variant="body2"
            sx={{ color: STATUS_COLOR[row.status], fontWeight: 500 }}
          >
            {row.status}
          </Typography>
        ),
      },
      {
        accessorKey: "progress",
        header: "Progress",
        size: 170,
        accessorFn: (row) => (
          <Typography variant="body2">{row.progress ?? "—"}</Typography>
        ),
      },
      {
        accessorKey: "app",
        header: "App",
        size: 130,
        accessorFn: (row) => (
          <Chip label={row.app} size="small" variant="outlined" />
        ),
      },
      {
        accessorKey: "reps",
        header: "Reps (N)",
        size: 90,
        accessorFn: (row) => (
          <Typography variant="body2">{row.reps}</Typography>
        ),
      },
      {
        accessorKey: "probes",
        header: "Probes",
        size: 180,
        accessorFn: (row) => (
          <Tooltip title={row.probes} placement="top">
            <Typography
              variant="body2"
              sx={{
                textOverflow: "ellipsis",
                overflow: "hidden",
                whiteSpace: "nowrap",
              }}
            >
              {row.probes}
            </Typography>
          </Tooltip>
        ),
      },
      {
        accessorKey: "started",
        header: "Started",
        size: 170,
        accessorFn: (row) => (
          <Typography variant="body2">{row.started}</Typography>
        ),
      },
      {
        accessorKey: "duration",
        header: "Duration",
        size: 110,
        accessorFn: (row) => (
          <Typography variant="body2">{row.duration}</Typography>
        ),
      },
      {
        accessorKey: "reproduced",
        header: "Reproduced",
        size: 200,
        accessorFn: (row) => (
          <Tooltip title={row.reproduced} placement="top">
            <Typography
              variant="body2"
              sx={{
                textOverflow: "ellipsis",
                overflow: "hidden",
                whiteSpace: "nowrap",
              }}
            >
              {row.reproduced}
            </Typography>
          </Tooltip>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        size: 260,
        enableSorting: false,
        enableColumnActions: false,
        accessorFn: (row) => {
          const isActive = row.status === "Running" || row.status === "Queued";
          return (
            <Stack direction="row" sx={{ gap: "4px", flexWrap: "wrap" }}>
              <Button
                size="small"
                onClick={() => onViewReport?.(row.id)}
                disabled={isActive}
              >
                Report
              </Button>
              <Button
                size="small"
                onClick={() => onOpenBundle?.(row.id)}
                disabled={isActive}
              >
                Bundle
              </Button>
              {isActive ? (
                <Button
                  size="small"
                  color="negative"
                  onClick={() => onCancel?.(row.id)}
                >
                  Cancel
                </Button>
              ) : (
                <Button
                  size="small"
                  onClick={() => onReRun?.(row.id)}
                >
                  Re-run
                </Button>
              )}
            </Stack>
          );
        },
      },

      {
        id: "traces",
        header: "Traces",
        size: 90,
        accessorFn: (row) => (
          <Typography variant="body2">{row.traces ?? "—"}</Typography>
        ),
      },
      {
        id: "cost",
        header: "Cost",
        size: 100,
        accessorFn: (row) => (
          <Typography variant="body2">{row.cost ?? "—"}</Typography>
        ),
      },
      {
        id: "agentModel",
        header: "Agent Model",
        size: 160,
        accessorFn: (row) => (
          <Typography variant="body2">{row.agentModel ?? "—"}</Typography>
        ),
      },
      {
        id: "failures",
        header: "Failures",
        size: 90,
        accessorFn: (row) => (
          <Typography
            variant="body2"
            sx={{ color: (row.failures ?? 0) > 0 ? "error.main" : undefined }}
          >
            {row.failures ?? 0}
          </Typography>
        ),
      },
      {
        id: "query",
        header: "Query",
        size: 220,
        accessorFn: (row) => (
          <Tooltip title={row.query ?? ""} placement="top">
            <Typography
              variant="body2"
              sx={{
                textOverflow: "ellipsis",
                overflow: "hidden",
                whiteSpace: "nowrap",
              }}
            >
              {row.query ?? "—"}
            </Typography>
          </Tooltip>
        ),
      },
    ],
    [onViewReport, onOpenBundle, onCancel, onReRun],
  );

  const tableRef = CreateTableInstance({
    data,
    columns,
    isLoading,
    rowCount: data.length,
    title: { label: "" },
    topToolbarProps: {
      export: { enableExport: false },
    },
    enableSorting: true,
    enableColumnResizing: true,
    renderEmptyRowsFallback: () => (
      <EmptyState title="No Runs" description="No IoC runs recorded yet." />
    ),
    state: { columnVisibility, sorting },
    onColumnVisibilityChange: setColumnVisibility,
    onSortingChange: setSorting,
    muiTableBodyRowProps: {
      sx: {
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        "& > td": {
          backgroundColor: `${GLOBAL_BACKGROUND_COLOR} !important`,
        },
      },
    },
    muiTablePaperProps: {
      sx: {
        padding: 0,
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        elevation: 0,
      },
    },
    muiTableHeadCellProps: {
      sx: { backgroundColor: GLOBAL_BACKGROUND_COLOR, color: "#ffffff" },
    },
    muiTableBodyCellProps: {
      sx: {
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        color: "#ffffff",
        height: "40px",
      },
    },
  });

  return <MaterialReactTable table={tableRef} />;
};
