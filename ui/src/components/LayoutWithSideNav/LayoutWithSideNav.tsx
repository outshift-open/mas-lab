//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Sidebar } from "@/components/Sidebar";
import { Outlet } from "react-router";
import { Box, Stack } from "@mui/material";

const LayoutWithSideNav = () => {
  return (
    <Stack direction={"column"} sx={{ height: "100%", width: "100%" }}>
      <Stack direction={"row"} sx={{ flex: 1 }}>
        <Sidebar />

        <Box sx={{ overflow: "hidden", width: "100%" }}>
          <Outlet />
        </Box>
      </Stack>
    </Stack>
  );
};

export default LayoutWithSideNav;
