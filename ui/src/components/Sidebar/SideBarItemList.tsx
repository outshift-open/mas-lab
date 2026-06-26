//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { List, Stack } from "@mui/material";
import { SideBarItem } from "./SideBarItem";
import {
  authenticatedRoutes,
  unauthenticatedRoutes,
} from "@/routes/routes.tsx";
import { useLocation } from "react-router";
import type { AppRoute } from "@/routes/types.ts";

export const SideBarItemList = () => {
  const { pathname } = useLocation();

  const library = pathname.split("/")[1] || "";

  const isUserAuthenticated = true;

  const allRoutes = [
    ...unauthenticatedRoutes,
    ...(isUserAuthenticated ? authenticatedRoutes : []),
  ];

  const resolvePath = (routePath: string) =>
    routePath.replace(":library", library);

  const isParentRouteSelected = (route: AppRoute) => {
    const resolved = resolvePath(route.path);
    if (resolved === "/") {
      return pathname === "/";
    }
    return pathname.startsWith(resolved);
  };

  return (
    <List
      sx={{
        gap: "4px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {allRoutes
        .map((parentRoute) => {
          return parentRoute.sideBarProps ? (
            <Stack
              direction={"column"}
              sx={{ gap: "4px" }}
              key={parentRoute.sideBarProps.title}
            >
              <SideBarItem
                {...parentRoute.sideBarProps}
                selected={isParentRouteSelected(parentRoute)}
                to={resolvePath(parentRoute.path)}
              />
            </Stack>
          ) : null;
        })
        .filter(Boolean)}
    </List>
  );
};
