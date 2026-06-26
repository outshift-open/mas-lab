//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Components, Theme } from "@mui/material";
import { colorTokens } from "./colors";

export const buttonComponent = (theme: Theme): Components => {
  return {
    MuiButtonBase: {
      defaultProps: {
        disableRipple: true,
      },
    },
    MuiButton: {
      defaultProps: {
        disableRipple: true,
        variant: "primary",
        color: "default",
        size: "medium",
      },
      styleOverrides: {
        root: {
          color: colorTokens.defaultColorText,
          textTransform: "none",
          transition: "none",
          borderRadius: "4px",
          "&:focus, &:focus-visible, &.Mui-focusVisible": {
            outline: "none !important",
            boxShadow: "none !important",
          },
          "& .MuiButton-startIcon": {
            marginLeft: "0px",
          },
          "&:has(>svg:only-child )": {
            "&.MuiButton-sizeLarge": {
              padding: "8px",
              minWidth: "40px",
              width: "40px",
            },
            "&.MuiButton-sizeMedium": {
              padding: "6px",
              minWidth: "32px",
              width: "32px",
            },
            "&.MuiButton-sizeSmall": {
              padding: "2px",
              minWidth: "24px",
              width: "24px",
            },
          },
          "& .MuiButton-endIcon": {
            marginRight: "0px",
          },
          "&.MuiButton-sizeLarge": {
            ...theme.typography.subtitle1,
            height: "40px",
          },
          "&.MuiButton-sizeMedium": {
            ...theme.typography.subtitle2,
            height: "32px",
          },
          "&.MuiButton-sizeLarge svg": {
            fontSize: "24px",
          },
          "&.MuiButton-sizeMedium svg, &.MuiButton-sizeSmall svg": {
            fontSize: "20px",
          },
          "&.MuiButton-primarySizeLarge, &.MuiButton-primarySizeMedium, &.MuiButton-secondarySizeLarge, &.MuiButton-secondarySizeMedium":
            {
              paddingRight: "16px",
              paddingLeft: "16px",
              "&:active": {
                paddingRight: "15px",
                paddingLeft: "15px",
              },
            },
          "&.MuiButton-tertariarySizeLarge, &.MuiButton-tertariarySizeMedium": {
            paddingRight: "16px",
            paddingLeft: "16px",
            "&:focus": {
              paddingRight: "14px",
              paddingLeft: "14px",
            },
          },
          "&.MuiButton-sizeSmall": {
            ...theme.typography.subtitle2,
            height: "24px",
            padding: "2px 12px",
            "&.MuiButton-primarySizeSmall:active, &.MuiButton-secondarySizeSmall:active":
              {
                paddingRight: "11px",
                paddingLeft: "11px",
              },
            "&.MuiButton-tertariarySizeSmall:focus": {
              paddingRight: "10px",
              paddingLeft: "10px",
            },
          },
          "&.MuiButton-primary": {
            background: colorTokens.interactivePrimaryDefaultDefault,
            "&.Mui-disabled": {
              background: colorTokens.disabledBackground,
              color: colorTokens.inverseColorText,
              opacity: 0.4,
            },
            "&:hover": {
              background: colorTokens.hoverBackground,
              color: colorTokens.inverseColorText,
            },
            "&:active": {
              background: colorTokens.interactivePrimaryDefaultDefault,
              border: `1px solid ${colorTokens.interactivePrimaryDefaultDefault}`,
            },
            "&:focus": {
              outline: `2px solid ${colorTokens.hoverBackground}`,
              outlineOffset: "2px",
            },
            "&.MuiButton-loading": {
              opacity: 1,
              background: colorTokens.interactivePrimaryDefaultDefault,
            },
          },
          "&.MuiButton-secondary": {
            background: colorTokens.surfaceLight300,
            color: colorTokens.baseTextInverse,
            "&.Mui-disabled": {
              background: colorTokens.secondaryDefaultDisabled,
              color: colorTokens.inverseColorText,
              opacity: 0.35,
            },
            "&:hover": {
              background: colorTokens.surfaceLight100,
            },
            "&&:active": {
              background: colorTokens.surfaceLight600,
              border: `1px solid ${colorTokens.surfaceLight600}`,
            },
            "&:focus": {
              outline: `2px solid ${colorTokens.hoverBackground}`,
              outlineOffset: "2px",
              border: "none",
            },
            "&.MuiButton-loading": {
              opacity: 1,
              background: colorTokens.surfaceLight300,
            },
          },
          "&.MuiButton-outlined": {
            border: `2px solid ${theme.palette.vars.interactiveTertiaryDefault}`,
            background: "none",
            color: theme.palette.vars.interactiveTextInDefault,
            "&:hover": {
              border: `2px solid ${theme.palette.vars.interactiveTertiaryHover}`,
              color: theme.palette.vars.interactiveTextInHover,
            },
            "&:active": {
              border: `2px solid ${theme.palette.vars.interactiveTertiaryActive}`,
              color: theme.palette.vars.interactiveTextInActive,
            },
            "&:focus": {
              outline: `2px solid ${theme.palette.vars.excellentBackgroundDefault}`,
              outlineOffset: "2px",
            },
            "&.Mui-disabled": {
              border: `2px solid ${theme.palette.vars.interactiveTertiaryDisabled}`,
              color: theme.palette.vars.baseTextWeak,
              opacity: 0.3,
            },
            "&.MuiButton-loading": {
              opacity: 1,
              border: `2px solid ${theme.palette.vars.interactiveTertiaryDefault}`,
              color: theme.palette.vars.interactiveTextInDefault,
            },
          },
          "&.MuiButton-tertariary": {
            background: "none",
            color: colorTokens.blue1Text,
            "&:hover": {
              color: colorTokens.hoverBlue1Text,
            },
            "&:active": {
              color: colorTokens.activeBlue1Text,
            },
            "&:focus": {
              border: `2px solid ${theme.palette.vars.excellentBackgroundDefault}`,
            },
            "&.Mui-disabled": {
              color: colorTokens.disabledBlue1Text,
              opacity: 0.4,
            },
            "&.MuiButton-loading": {
              opacity: 1,
              color: colorTokens.interactivePrimaryDefaultDefault,
            },
          },
        },
      },
      variants: [
        {
          props: {
            color: "negative",
          },
          style: {
            "&.MuiButton-primary.MuiButton-colorNegative": {
              background: colorTokens.negativeBackgroundDefault,
              "&.Mui-disabled": {
                opacity: 0.35,
                background: colorTokens.negativeBackgroundDisabled,
                color: colorTokens.defaultColorText,
              },
              "&:hover": {
                color: colorTokens.defaultColorText,
                background: colorTokens.negativeBackgroundHover,
              },
              "&:active": {
                background: colorTokens.negativeBackgroundDefault,
                border: `1px solid ${colorTokens.negativeActiveBorderDefault}`,
              },
              "&:focus": {
                outline: `2px solid ${colorTokens.hoverBackground}`,
                outlineOffset: "2px",
              },
              "&.MuiButton-loading": {
                opacity: 1,
                color: colorTokens.defaultColorText,
                background: colorTokens.negativeBackgroundDefault,
              },
            },
            "&.MuiButton-outlined.MuiButton-colorNegative": {
              border: `2px solid ${theme.palette.vars.negativeBorderDefault}`,
              background: "none",
              color: theme.palette.vars.negativeBackgroundActive,
              "&:hover": {
                border: `2px solid ${theme.palette.vars.negativeBackgroundHover}`,
                color: theme.palette.vars.negativeBackgroundHover,
              },
              "&:active": {
                border: `2px solid ${theme.palette.vars.negativeBackgroundActive}`,
                color: theme.palette.vars.negativeBackgroundActive,
              },
              "&:focus": {
                outline: `2px solid ${theme.palette.vars.excellentBackgroundDefault}`,
                outlineOffset: "2px",
                color: theme.palette.vars.negativeBackgroundActive,
                border: `2px solid ${theme.palette.vars.negativeBackgroundActive}`,
              },
              "&.Mui-disabled": {
                border: `2px solid ${theme.palette.vars.negativeBackgroundDisabled}`,
                color: theme.palette.vars.negativeBackgroundDisabled,
                opacity: 0.35,
              },
              "&.MuiButton-loading": {
                opacity: 1,
                border: `2px solid ${theme.palette.vars.negativeBorderDefault}`,
                color: theme.palette.vars.negativeBackgroundActive,
              },
            },
            "&.MuiButton-tertariary": {
              background: "none",
              color: colorTokens.negativeTextDefault,
              "&:hover": {
                color: colorTokens.negativeBackgroundHover,
              },
              "&:active": {
                color: colorTokens.negativeTextActive,
              },
              "&:focus": {
                border: `2px solid ${colorTokens.hoverBackground}`,
              },
              "&.Mui-disabled": {
                color: colorTokens.negativeActiveBorderDefault,
              },
              "&.MuiButton-loading": {
                opacity: 1,
                color: colorTokens.negativeTextDefault,
              },
            },
          },
        },
      ],
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          padding: 0,
        },
      },
      variants: [
        {
          props: { color: "default" },
          style: {
            color: theme.palette.vars.brandIconPrimaryDefault,
          },
        },
      ],
    },
  };
};
