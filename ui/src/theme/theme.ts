//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Theme, createTheme } from "@mui/material/styles";
import { buttonComponent } from "./button";

export const createLocalTheme = (outerTheme: Theme): Theme =>
  createTheme(outerTheme, {
    components: {
      ...buttonComponent(outerTheme),
    },
  });
