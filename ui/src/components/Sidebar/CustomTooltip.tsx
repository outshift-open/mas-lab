//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import Tooltip, { type TooltipProps } from "@mui/material/Tooltip";
import { sideBarTooltip } from "./styles";
import { useTheme } from "@mui/material";

export type SideBarTooltipProps = TooltipProps;

export default function CustomTooltip(props: SideBarTooltipProps) {
  const theme = useTheme();
  return (
    <Tooltip {...props} sx={sideBarTooltip(theme)}>
      {props.children}
    </Tooltip>
  );
}
