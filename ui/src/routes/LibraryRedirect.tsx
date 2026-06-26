//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Navigate } from "react-router";
import { useLibraries } from "@/api/apiCalls";
import { Box, CircularProgress } from "@mui/material";

export function LibraryRedirect() {
  const { data: libraries, isLoading } = useLibraries();

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  const firstLib = libraries?.[0]?.dir;
  if (firstLib) {
    return <Navigate to={`/${firstLib}/applications`} replace />;
  }

  return <Navigate to="/applications" replace />;
}
