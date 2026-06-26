//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import "@open-ui-kit/core/typography.css";
import "@xyflow/react/dist/style.css";
import { ThemeProvider } from "@open-ui-kit/core";
import { ThemeProvider as MuiThemeProvider, useTheme } from "@mui/material/styles";
import { BrowserRouter as Router } from "react-router";
import { Box, CssBaseline } from "@mui/material";
import { TopBar } from "@/components";
import AppRoutes from "@/routes/routes.tsx";

import { QueryClientProvider } from "@/provider";
import { GLOBAL_BACKGROUND_COLOR } from "@/common/styles";
import { createLocalTheme } from "@/theme/theme";

function ThemedApp() {
  const outerTheme = useTheme();
  const localTheme = createLocalTheme(outerTheme);

  return (
    <MuiThemeProvider theme={localTheme}>
      <CssBaseline />
      <Router>
        <Box
          sx={{
            height: "100%",
            width: "100%",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <TopBar />
          <Box sx={{ flex: 1, backgroundColor: GLOBAL_BACKGROUND_COLOR }}>
            <AppRoutes />
          </Box>
        </Box>
      </Router>
    </MuiThemeProvider>
  );
}

const App = () => {
  return (
    <QueryClientProvider>
      <ThemeProvider defaultDarkMode>
        <ThemedApp />
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
